using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Aive.UI2.Announcements;

public sealed class AnnouncementService : IAsyncDisposable
{
	public const int MaximumResponseBytes = 2000000;

	private readonly AnnouncementOptions options;

	private readonly HttpClient http;

	private readonly AnnouncementCache cache;

	private readonly Action<string> log;

	private readonly SemaphoreSlim refreshGate = new SemaphoreSlim(1, 1);

	private readonly CancellationTokenSource lifetime = new CancellationTokenSource();

	private readonly object stateGate = new object();

	private readonly TimeProvider time;

	private readonly TimeSpan validityInterval;

	private Task? runner;

	private IReadOnlyList<Announcement> all = Array.Empty<Announcement>();

	private AnnouncementSnapshot snapshot = new AnnouncementSnapshot(Array.Empty<Announcement>(), null, FromCache: false);

	public AnnouncementSnapshot Snapshot
	{
		get
		{
			lock (stateGate)
			{
				return snapshot;
			}
		}
	}

	public event Action<AnnouncementSnapshot>? Changed;

	public AnnouncementService(AnnouncementOptions options, Action<string> log, HttpClient? http = null, TimeProvider? time = null, TimeSpan? validityInterval = null)
	{
		this.options = options;
		this.log = log;
		this.time = time ?? TimeProvider.System;
		this.validityInterval = validityInterval ?? TimeSpan.FromSeconds(30.0);
		this.http = http ?? new HttpClient(new HttpClientHandler
		{
			AllowAutoRedirect = false
		})
		{
			Timeout = TimeSpan.FromSeconds(12.0)
		};
		cache = new AnnouncementCache(options);
		if (!AnnouncementUrlPolicy.TryGetWebUri(options.Endpoint.AbsoluteUri, out Uri _) || string.IsNullOrWhiteSpace(options.ProductId) || string.IsNullOrWhiteSpace(options.Version) || options.RefreshInterval <= TimeSpan.Zero)
		{
			throw new ArgumentException("Invalid announcement options");
		}
	}

	public void Start()
	{
		if (runner == null)
		{
			runner = Task.Run((Func<Task?>)RunAsync);
		}
	}

	private async Task RunAsync()
	{
		CancellationToken token = lifetime.Token;
		try
		{
			try
			{
				AnnouncementSnapshot cached = await cache.ReadAsync(token, log).ConfigureAwait(continueOnCapturedContext: false);
				if (cached != null)
				{
					lock (stateGate)
					{
						all = cached.Items;
						snapshot = cached;
					}
					PublishValidity();
					log($"Announcement cache loaded: {Snapshot.Items.Count} valid items");
				}
			}
			catch (Exception ex) when (!(ex is OperationCanceledException))
			{
				log("Warning: announcement cache ignored: " + ex.GetType().Name);
			}
			Task refresh = RefreshAsync(token);
			DateTimeOffset nextRefresh = time.GetUtcNow() + options.RefreshInterval;
			using PeriodicTimer timer = new PeriodicTimer(validityInterval, time);
			while (await timer.WaitForNextTickAsync(token).ConfigureAwait(continueOnCapturedContext: false))
			{
				PublishValidity();
				if (time.GetUtcNow() >= nextRefresh && refresh.IsCompleted)
				{
					await refresh.ConfigureAwait(continueOnCapturedContext: false);
					refresh = RefreshAsync(token);
					nextRefresh = time.GetUtcNow() + options.RefreshInterval;
				}
			}
			await refresh.ConfigureAwait(continueOnCapturedContext: false);
		}
		catch (OperationCanceledException) when (token.IsCancellationRequested)
		{
		}
		catch (Exception ex3)
		{
			log("Warning: announcement loop stopped: " + ex3.GetType().Name);
		}
	}

	public async Task RefreshAsync(CancellationToken cancellationToken = default(CancellationToken))
	{
		using CancellationTokenSource linked = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, cancellationToken);
		CancellationToken token = linked.Token;
		if (!(await refreshGate.WaitAsync(0, token).ConfigureAwait(continueOnCapturedContext: false)))
		{
			return;
		}
		linked.CancelAfter(TimeSpan.FromSeconds(12.0));
		try
		{
			log("Announcement fetch started");
			using HttpResponseMessage response = await http.GetAsync(options.RequestUri, HttpCompletionOption.ResponseHeadersRead, token).ConfigureAwait(continueOnCapturedContext: false);
			response.EnsureSuccessStatusCode();
			if (response.Content.Headers.ContentLength > 2000000)
			{
				throw new JsonException("Response too large");
			}
			await using Stream stream = await response.Content.ReadAsStreamAsync(token).ConfigureAwait(continueOnCapturedContext: false);
			using MemoryStream buffer = new MemoryStream();
			byte[] bytes = new byte[8192];
			int count;
			while ((count = await stream.ReadAsync(bytes, token).ConfigureAwait(continueOnCapturedContext: false)) != 0)
			{
				if (buffer.Length + count > 2000000)
				{
					throw new JsonException("Response too large");
				}
				buffer.Write(bytes, 0, count);
			}
			IReadOnlyList<Announcement> items = AnnouncementParser.Parse(buffer.ToArray(), options.ProductId, log);
			DateTimeOffset fetched = time.GetUtcNow();
			lock (stateGate)
			{
				all = items;
				snapshot = new AnnouncementSnapshot(snapshot.Items, fetched, FromCache: false);
			}
			try
			{
				await cache.WriteAsync(items, fetched, token).ConfigureAwait(continueOnCapturedContext: false);
			}
			catch (Exception ex) when (!(ex is OperationCanceledException))
			{
				log("Warning: announcement cache write failed: " + ex.GetType().Name);
			}
			PublishValidity(force: true);
			log($"Announcement refresh succeeded: {items.Count} returned, {Snapshot.Items.Count} valid");
		}
		catch (OperationCanceledException) when (lifetime.IsCancellationRequested || cancellationToken.IsCancellationRequested)
		{
		}
		catch (Exception ex3)
		{
			log("Warning: announcement fetch/parse failed: " + ex3.GetType().Name);
			lock (stateGate)
			{
				snapshot = snapshot with
				{
					FromCache = true
				};
			}
			PublishValidity(force: true);
			log($"Announcement fallback: {Snapshot.Items.Count} cached valid items");
		}
		finally
		{
			refreshGate.Release();
		}
	}

	private void PublishValidity(bool force = false)
	{
		AnnouncementSnapshot updated;
		lock (stateGate)
		{
			DateTimeOffset now = time.GetUtcNow();
			Announcement[] items = ((snapshot.LastFetchTime.HasValue && now - snapshot.LastFetchTime.Value <= TimeSpan.FromDays(7.0)) ? all.Where((Announcement item) => item.IsValidAt(now)).ToArray() : Array.Empty<Announcement>());
			if (!force && items.SequenceEqual(snapshot.Items))
			{
				return;
			}
			updated = (snapshot = snapshot with
			{
				Items = items
			});
		}
		try
		{
			this.Changed?.Invoke(updated);
		}
		catch (Exception ex)
		{
			log("Warning: announcement UI notification failed: " + ex.GetType().Name);
		}
	}

	public async ValueTask DisposeAsync()
	{
		lifetime.Cancel();
		if (runner != null)
		{
			await runner.ConfigureAwait(continueOnCapturedContext: false);
		}
		await refreshGate.WaitAsync().ConfigureAwait(continueOnCapturedContext: false);
		refreshGate.Release();
		http.Dispose();
		lifetime.Dispose();
		refreshGate.Dispose();
	}
}
