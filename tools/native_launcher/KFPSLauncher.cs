using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Forms;

internal static class KfpsLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string appRoot = ResolveAppRoot(baseDir);
            string python = Path.Combine(appRoot, "python", "pythonw.exe");
            if (!File.Exists(python))
            {
                python = Path.Combine(appRoot, "python", "python.exe");
            }
            string app = Path.Combine(appRoot, "KFPS.UI", "app.py");

            if (!File.Exists(python) || !File.Exists(app))
            {
                MessageBox.Show(
                    "KFPS could not find its bundled Python runtime or UI files.\n\n" +
                    "Keep KFPS.exe beside the KloudysFH6Painter folder, then run the updater or reinstall the bundled release.",
                    "KFPS launch failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 2;
            }

            string arguments = Quote(app);
            if (args.Length > 0)
            {
                arguments += " " + string.Join(" ", args.Select(Quote));
            }

            ProcessStartInfo info = new ProcessStartInfo
            {
                FileName = python,
                Arguments = arguments,
                WorkingDirectory = appRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            info.EnvironmentVariables["KFPS_APP_ROOT"] = appRoot;
            using (Process process = Process.Start(info))
            {
                if (process == null)
                {
                    return 3;
                }
                if (args.Length > 0)
                {
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "KFPS launch failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static string ResolveAppRoot(string baseDir)
    {
        string nested = Path.Combine(baseDir, "KloudysFH6Painter");
        if (LooksLikeAppRoot(nested))
        {
            return nested;
        }
        if (LooksLikeAppRoot(baseDir))
        {
            return baseDir;
        }
        return nested;
    }

    private static bool LooksLikeAppRoot(string path)
    {
        return Directory.Exists(path)
            && File.Exists(Path.Combine(path, "VERSION"))
            && File.Exists(Path.Combine(path, "KFPS.UI", "app.py"));
    }

    private static string Quote(string value)
    {
        if (value == null)
        {
            return "\"\"";
        }
        StringBuilder builder = new StringBuilder();
        builder.Append('"');
        int backslashes = 0;
        foreach (char c in value)
        {
            if (c == '\\')
            {
                backslashes++;
                continue;
            }
            if (c == '"')
            {
                builder.Append('\\', backslashes * 2 + 1);
                builder.Append('"');
                backslashes = 0;
                continue;
            }
            builder.Append('\\', backslashes);
            backslashes = 0;
            builder.Append(c);
        }
        builder.Append('\\', backslashes * 2);
        builder.Append('"');
        return builder.ToString();
    }
}
