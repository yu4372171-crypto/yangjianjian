using System.ComponentModel;
using System.IO;
using System.Text.Json;
using System.Windows;
using Aive.UI2.Announcements;
using Aive.UI2.Bridge;
using Microsoft.Web.WebView2.Core;

namespace Aive.UI2;

public partial class MainWindow : Window
{
    private readonly PythonBackend backend = new();
    private readonly LocalMedia media = new();
    private bool closing;
    private bool closed;
    private bool ready;
    private bool forceExit;
    private WebBridge? bridge;
    private AnnouncementHost? announcements;

    public MainWindow()
    {
        InitializeComponent();
        SourceInitialized += (_, _) => WorkAreaBounds.Attach(this);
    }

    private async void OnLoaded(object sender, RoutedEventArgs args)
    {
        try
        {
            var options = new CoreWebView2EnvironmentOptions();
            string? debugPort = Environment.GetEnvironmentVariable("AIVE_UI2_DEBUG_PORT");
            if (int.TryParse(debugPort, out int port) && port is > 1024 and < 65536)
            {
                options.AdditionalBrowserArguments = $"--remote-debugging-port={port}";
            }

            bool debugEnabled = !string.IsNullOrWhiteSpace(debugPort);
            HostLog.Write($"WebView2 startup (debug port: {(debugEnabled ? debugPort : "disabled")}).");

            string userDataFolder = Path.Combine(HostLog.DataDirectory, "webview2");
            CoreWebView2Environment environment =
                await CoreWebView2Environment.CreateAsync(null, userDataFolder, options);
            await Web.EnsureCoreWebView2Async(environment);
            HostLog.Write("WebView2 initialization completed.");

            CoreWebView2 core = Web.CoreWebView2;
            core.Settings.AreDefaultContextMenusEnabled = debugEnabled;
            core.Settings.AreDevToolsEnabled = debugEnabled;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsNonClientRegionSupportEnabled = true;
            core.AddWebResourceRequestedFilter(
                "https://media.aive.local/*",
                CoreWebView2WebResourceContext.All);
            core.WebResourceRequested += (_, eventArgs) => media.Respond(core, eventArgs);

            announcements = new AnnouncementHost(backend, snapshot =>
            {
                if (closing || closed || Dispatcher.HasShutdownStarted)
                {
                    return;
                }

                _ = Dispatcher.InvokeAsync(() =>
                {
                    if (!closed)
                    {
                        core.PostWebMessageAsJson(JsonSerializer.Serialize(new
                        {
                            @event = "announcement.changed",
                            data = snapshot
                        }, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
                    }
                });
            });

            bridge = new WebBridge(this, core, backend, media, announcements);
            bridge.CloseRequested += AskToClose;
            core.WebMessageReceived += bridge.Receive;

            backend.EventReceived += packet =>
            {
                _ = Dispatcher.InvokeAsync(async () =>
                {
                    if (packet.TryGetProperty("event", out JsonElement eventElement) &&
                        eventElement.GetString() == "license.changed" &&
                        packet.TryGetProperty("data", out JsonElement data) &&
                        data.TryGetProperty("required", out JsonElement required) &&
                        required.GetBoolean() &&
                        announcements is not null)
                    {
                        await announcements.StopAsync();
                    }

                    if (!closed)
                    {
                        media.Register(packet);
                        core.PostWebMessageAsJson(packet.GetRawText());
                    }
                });
            };

            backend.Failed += message =>
            {
                _ = Dispatcher.InvokeAsync(() =>
                    core.PostWebMessageAsJson(JsonSerializer.Serialize(new
                    {
                        @event = "backend.failed",
                        data = new { message }
                    })));
            };

            core.NavigationStarting += (_, eventArgs) =>
            {
                Uri uri = new(eventArgs.Uri);
                bool trusted = uri.Host == "app.aive.local" ||
                               (uri.Host == "localhost" && uri.Port == 5173);
                if (!trusted)
                {
                    eventArgs.Cancel = true;
                }
            };
            core.NewWindowRequested += (_, eventArgs) => eventArgs.Handled = true;

            backend.Start();

            if (Environment.GetEnvironmentVariable("AIVE_UI2_DEV") == "1")
            {
                core.Navigate("http://localhost:5173/");
            }
            else
            {
                string webUiFolder = Path.Combine(AppContext.BaseDirectory, "WebUI");
                if (!File.Exists(Path.Combine(webUiFolder, "index.html")))
                {
                    throw new FileNotFoundException("缺少 WebUI 静态资源，请先运行构建脚本。");
                }

                core.SetVirtualHostNameToFolderMapping(
                    "app.aive.local",
                    webUiFolder,
                    CoreWebView2HostResourceAccessKind.DenyCors);
                core.Navigate("https://app.aive.local/index.html");
            }

            ready = true;
            StartupPanel.Visibility = Visibility.Collapsed;
        }
        catch (Exception exception)
        {
            HostLog.Write(exception.ToString());
            StartupLabel.Text =
                $"启动失败：{exception.Message}\n详细信息已写入 ui2-host.log";
        }
    }

    private void AskToClose(bool force)
    {
        forceExit = force;
        Close();
    }

    private async void OnClosing(object? sender, CancelEventArgs args)
    {
        if (closed)
        {
            return;
        }

        args.Cancel = true;
        if (closing)
        {
            return;
        }

        closing = true;
        try
        {
            if (ready && !forceExit)
            {
                JsonElement request = JsonSerializer.SerializeToElement(new
                {
                    id = Guid.NewGuid().ToString(),
                    action = "task.getList",
                    data = new { }
                });
                int active = 0;
                JsonElement response = await backend.InvokeAsync(request);
                if (response.TryGetProperty("data", out JsonElement list) &&
                    list.ValueKind == JsonValueKind.Array)
                {
                    active = list.EnumerateArray().Count(task =>
                    {
                        string? status = task.TryGetProperty("status", out JsonElement value)
                            ? value.GetString()
                            : null;
                        return status is "running" or "queued" or "paused" or "cancelling";
                    });
                }

                Web.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new
                {
                    @event = "app.closeRequested",
                    data = new { active }
                }));
                closing = false;
                return;
            }
        }
        catch (Exception exception)
        {
            HostLog.Write($"Close check: {exception.Message}");
        }

        if (announcements is not null)
        {
            await announcements.DisposeAsync();
        }

        await backend.DisposeAsync();
        Web.Dispose();
        closed = true;
        Close();
    }
}
