using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Aive.UI2.Bridge;

namespace Aive.UI2.Announcements;

public sealed class AnnouncementHost(PythonBackend backend, Action<AnnouncementSnapshot> publish) : IAsyncDisposable
{
	private readonly SemaphoreSlim lifecycle = new SemaphoreSlim(1, 1);

	private AnnouncementService? service;

	private bool disposed;

	private static AnnouncementSnapshot Empty => new AnnouncementSnapshot(Array.Empty<Announcement>(), null, FromCache: false);

	public async Task<AnnouncementSnapshot> StartAsync()
	{
		await lifecycle.WaitAsync();
		try
		{
			AnnouncementSnapshot result = default(AnnouncementSnapshot);
			object obj;
			int num;
			try
			{
				if (disposed)
				{
					result = Empty;
					return result;
				}
				JsonElement request = JsonSerializer.SerializeToElement(new
				{
					id = Guid.NewGuid().ToString(),
					action = "settings.getAnnouncementConfig",
					data = new { }
				});
				JsonElement response = await backend.InvokeAsync(request);
				if (response.GetProperty("success").GetBoolean())
				{
					JsonElement config = response.GetProperty("data");
					string product = config.GetProperty("productId").GetString();
					string? value = config.GetProperty("serverUrl").GetString();
					string path = config.GetProperty("apiPath").GetString();
					if (!AnnouncementUrlPolicy.TryGetWebUri(value, out Uri baseUri) || !path.StartsWith('/') || path.StartsWith("//") || !Uri.TryCreate(baseUri, path, out Uri endpoint) || endpoint.Authority != baseUri.Authority || !AnnouncementUrlPolicy.TryGetWebUri(endpoint.AbsoluteUri, out Uri _))
					{
						throw new ArgumentException("Invalid announcement API path");
					}
					AssemblyInformationalVersionAttribute? customAttribute = typeof(AnnouncementHost).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>();
					string version = ((customAttribute != null) ? customAttribute.InformationalVersion.Split('+')[0] : null) ?? typeof(AnnouncementHost).Assembly.GetName().Version.ToString();
					TimeSpan interval = TimeSpan.FromMinutes(Math.Clamp(config.GetProperty("refreshMinutes").GetInt32(), 30, 60));
					if (service != null)
					{
						result = service.Snapshot;
						return result;
					}
					service = new AnnouncementService(new AnnouncementOptions(product, version, endpoint, Path.Combine(HostLog.DataDirectory, "cache", "announcements"), interval), HostLog.Write);
					service.Changed += publish;
					service.Start();
					result = service.Snapshot;
					return result;
				}
				await StopCoreAsync();
				result = Empty;
				return result;
			}
			catch (Exception ex)
			{
				obj = ex;
				num = 1;
			}
			if (num != 1)
			{
				return result;
			}
			Exception exc = (Exception)obj;
			HostLog.Write("Warning: announcement initialization failed: " + exc.GetType().Name);
			await StopCoreAsync();
			return Empty;
		}
		finally
		{
			lifecycle.Release();
		}
	}

	public bool OpenLink(string id)
	{
		Announcement item = service?.Snapshot.Items.FirstOrDefault((Announcement x) => x.Id == id && x.IsValidAt(DateTimeOffset.UtcNow));
		if (item == null || !AnnouncementUrlPolicy.TryGetWebUri(item.LinkUrl, out Uri uri))
		{
			HostLog.Write("Warning: announcement URL blocked or announcement inactive");
			return false;
		}
		try
		{
			Process.Start(new ProcessStartInfo(uri.AbsoluteUri)
			{
				UseShellExecute = true
			});
			return true;
		}
		catch (Exception ex)
		{
			HostLog.Write("Warning: announcement link open failed: " + ex.GetType().Name);
			return false;
		}
	}

	public async Task StopAsync()
	{
		await lifecycle.WaitAsync();
		try
		{
			await StopCoreAsync();
		}
		finally
		{
			lifecycle.Release();
		}
	}

	private async Task StopCoreAsync()
	{
		AnnouncementService previous = service;
		service = null;
		if (previous != null)
		{
			previous.Changed -= publish;
			await previous.DisposeAsync();
		}
		publish(Empty);
	}

	public async ValueTask DisposeAsync()
	{
		await lifecycle.WaitAsync();
		try
		{
			disposed = true;
			await StopCoreAsync();
		}
		finally
		{
			lifecycle.Release();
		}
	}
}
