using System.Windows;
using System.Windows.Threading;

namespace Aive.UI2;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        base.OnStartup(e);
    }

    private static void OnDispatcherUnhandledException(
        object? sender,
        DispatcherUnhandledExceptionEventArgs args)
    {
        HostLog.Write(args.Exception.ToString());
        MessageBox.Show(
            $"界面运行出现异常，详细信息已写入日志。\n{args.Exception.Message}",
            "羊剪剪运行错误",
            MessageBoxButton.OK,
            MessageBoxImage.Error);
        args.Handled = true;
    }
}
