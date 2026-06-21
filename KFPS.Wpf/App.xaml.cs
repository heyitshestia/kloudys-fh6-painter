using System;
using System.IO;
using System.Windows;
using System.Windows.Threading;

namespace KFPS.Wpf;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += App_DispatcherUnhandledException;
        base.OnStartup(e);
    }

    private static void App_DispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        TryWriteUiErrorLog(e.Exception);
        MessageBox.Show(
            "KFPS caught a UI error and kept the app open.\n\n" + e.Exception.Message,
            "KFPS UI warning",
            MessageBoxButton.OK,
            MessageBoxImage.Warning);
        e.Handled = true;
    }

    private static void TryWriteUiErrorLog(Exception exception)
    {
        try
        {
            var exePath = Environment.ProcessPath;
            var baseFolder = !string.IsNullOrWhiteSpace(exePath)
                ? Path.GetDirectoryName(exePath)
                : AppContext.BaseDirectory;
            baseFolder ??= AppContext.BaseDirectory;

            var logPath = Path.Combine(baseFolder, "kfps-ui-error.log");
            File.AppendAllText(
                logPath,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}] {exception}\n\n");
        }
        catch
        {
            // The popup still keeps the app alive if logging itself is unavailable.
        }
    }
}
