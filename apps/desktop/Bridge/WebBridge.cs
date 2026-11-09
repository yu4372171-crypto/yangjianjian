using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using Aive.UI2.Announcements;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;

namespace Aive.UI2.Bridge;

public sealed class WebBridge(Window window, CoreWebView2 web, PythonBackend backend, LocalMedia media, AnnouncementHost announcements)
{
	public event Action<bool>? CloseRequested;

	public async void Receive(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
	{
		string id = null;
		try
		{
			if (new Uri(args.Source).Host != "app.aive.local" && !args.Source.StartsWith("http://localhost:5173/"))
			{
				throw new UnauthorizedAccessException("消息来源不受信任");
			}
			using JsonDocument doc = JsonDocument.Parse(args.WebMessageAsJson);
			JsonElement request = doc.RootElement;
			id = request.GetProperty("id").GetString();
			string action = request.GetProperty("action").GetString();
			JsonElement value;
			JsonElement data = (request.TryGetProperty("data", out value) ? value : JsonSerializer.SerializeToElement(new { }));
			object result;
			if (action.StartsWith("window."))
			{
				switch (action)
				{
				case "window.minimize":
					window.WindowState = WindowState.Minimized;
					break;
				case "window.maximize":
					window.WindowState = ((window.WindowState != WindowState.Maximized) ? WindowState.Maximized : WindowState.Normal);
					break;
				case "window.close":
					this.CloseRequested?.Invoke(obj: false);
					break;
				case "window.forceClose":
					this.CloseRequested?.Invoke(obj: true);
					break;
				default:
					throw new InvalidOperationException("未知窗口命令");
				}
				result = true;
			}
			else
			{
				bool flag;
				JsonElement response;
				switch (action)
				{
				case "announcement.start":
					result = JsonSerializer.SerializeToElement(await announcements.StartAsync(), new JsonSerializerOptions(JsonSerializerDefaults.Web));
					break;
				case "announcement.stop":
					await announcements.StopAsync();
					result = true;
					break;
				case "announcement.openLink":
					result = announcements.OpenLink(data.GetProperty("id").GetString());
					break;
				case "system.getFonts":
					result = (from font in Fonts.SystemFontFamilies
						select font.Source into name
						orderby name
						select name).ToArray();
					break;
				case "system.openUrl":
				{
					Uri uri = new Uri(data.GetProperty("url").GetString());
					string scheme = uri.Scheme;
					if (!(scheme == "http") && !(scheme == "https"))
					{
						throw new UnauthorizedAccessException("仅支持网页链接");
					}
					Process.Start(new ProcessStartInfo(uri.AbsoluteUri)
					{
						UseShellExecute = true
					});
					result = true;
					break;
				}
				case "file.select":
				{
					JsonElement multiple;
					JsonElement filter;
					OpenFileDialog dialog2 = new OpenFileDialog
					{
						Multiselect = (!data.TryGetProperty("multiple", out multiple) || multiple.GetBoolean()),
						Filter = (data.TryGetProperty("filter", out filter) ? filter.GetString() : "所有文件|*.*")
					};
					string[] files = ((dialog2.ShowDialog(window) == true) ? dialog2.FileNames : Array.Empty<string>());
					string[] array = files;
					foreach (string path2 in array)
					{
						media.Allow(path2);
					}
					result = files;
					break;
				}
				case "file.save":
				{
					string? text = data.GetProperty("contentBase64").GetString();
					if (text.Length > 14000000)
					{
						throw new InvalidOperationException("下载文件过大");
					}
					byte[] bytes = Convert.FromBase64String(text);
					JsonElement saveFilter;
					SaveFileDialog dialog = new SaveFileDialog
					{
						FileName = Path.GetFileName(data.GetProperty("name").GetString()),
						Filter = (data.TryGetProperty("filter", out saveFilter) ? saveFilter.GetString() : "所有文件|*.*"),
						AddExtension = true,
						OverwritePrompt = true
					};
					if (dialog.ShowDialog(window) == true)
					{
						await File.WriteAllBytesAsync(dialog.FileName, bytes);
						media.Allow(dialog.FileName);
						result = dialog.FileName;
					}
					else
					{
						result = "";
					}
					break;
				}
				case "folder.select":
				{
					OpenFolderDialog dialog3 = new OpenFolderDialog();
					result = ((dialog3.ShowDialog(window) == true) ? dialog3.FolderName : "");
					break;
				}
				case "media.getUrl":
					result = media.Url(data.GetProperty("path").GetString());
					break;
				case "file.reveal":
				case "file.open":
					flag = true;
					goto IL_0680;
				default:
					{
						flag = false;
						goto IL_0680;
					}
					IL_0680:
					if (flag)
					{
						string path = Path.GetFullPath(data.GetProperty("path").GetString());
						if (!media.IsAllowed(path))
						{
							throw new UnauthorizedAccessException("请先从项目选择该文件");
						}
						if (action == "file.reveal")
						{
							Process.Start(new ProcessStartInfo("explorer.exe")
							{
								ArgumentList = { "/select," + path }
							});
						}
						else
						{
							Process.Start(new ProcessStartInfo(path)
							{
								UseShellExecute = true
							});
						}
						result = true;
						break;
					}
					response = await backend.InvokeAsync(request);
					media.Register(response);
					web.PostWebMessageAsJson(response.GetRawText());
					return;
				}
			}
			web.PostWebMessageAsJson(JsonSerializer.Serialize(new
			{
				id = id,
				success = true,
				data = result,
				error = (object)null
			}));
		}
		catch (Exception ex)
		{
			HostLog.Write($"Bridge failure: {ex}");
			web.PostWebMessageAsJson(JsonSerializer.Serialize(new
			{
				id = id,
				success = false,
				data = (object)null,
				error = new
				{
					code = "HOST_ERROR",
					message = ex.Message
				}
			}));
		}
	}
}
