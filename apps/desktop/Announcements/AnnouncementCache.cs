using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Aive.UI2.Announcements;

public sealed class AnnouncementCache
{
	private sealed record CacheRecord(int Schema, string Scope, DateTimeOffset LastFetchTime, IReadOnlyList<Announcement> Items);

	private static readonly JsonSerializerOptions Json = new JsonSerializerOptions(JsonSerializerDefaults.Web);

	private readonly string scope;

	public string FilePath { get; }

	public AnnouncementCache(AnnouncementOptions options)
	{
		scope = options.ProductId + "\n" + options.Endpoint.AbsoluteUri;
		string key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(scope)));
		FilePath = Path.Combine(options.CacheDirectory, "announcements-" + key + ".json");
	}

	public async Task<AnnouncementSnapshot?> ReadAsync(CancellationToken token, Action<string>? log = null)
	{
		if (!File.Exists(FilePath))
		{
			return null;
		}
		if (new FileInfo(FilePath).Length > 2000000)
		{
			throw new JsonException("Cache too large");
		}
		AnnouncementSnapshot result;
		await using (FileStream file = File.OpenRead(FilePath))
		{
			CacheRecord record = await JsonSerializer.DeserializeAsync<CacheRecord>(file, Json, token).ConfigureAwait(continueOnCapturedContext: false);
			if ((object)record == null || record.Schema != 1 || record.Scope != scope || record.Items == null || record.Items.Count > 200 || record.LastFetchTime > DateTimeOffset.UtcNow.AddMinutes(5.0))
			{
				throw new JsonException("Invalid announcement cache");
			}
			IReadOnlyList<Announcement> items = AnnouncementParser.Parse(JsonSerializer.SerializeToUtf8Bytes(record.Items, Json), scope.Split('\n')[0], log ?? ((Action<string>)delegate
			{
			}));
			result = new AnnouncementSnapshot(items, record.LastFetchTime, FromCache: true);
		}
		return result;
	}

	public async Task WriteAsync(IReadOnlyList<Announcement> items, DateTimeOffset fetched, CancellationToken token)
	{
		Directory.CreateDirectory(Path.GetDirectoryName(FilePath));
		string temp = FilePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
		try
		{
			await using (FileStream file = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, useAsync: true))
			{
				await JsonSerializer.SerializeAsync(file, new CacheRecord(1, scope, fetched, items), Json, token).ConfigureAwait(continueOnCapturedContext: false);
			}
			File.Move(temp, FilePath, overwrite: true);
		}
		finally
		{
			if (File.Exists(temp))
			{
				File.Delete(temp);
			}
		}
	}
}
