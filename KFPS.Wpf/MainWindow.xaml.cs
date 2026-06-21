using Microsoft.Win32;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace KFPS.Wpf;

public partial class MainWindow : Window
{
    private readonly string _appRoot;
    private readonly List<ThemeDefinition> _themes;
    private bool _loadingSettings;
    private string? _selectedSourceImage;
    private string? _selectedJson;
    private string? _sourceHeatmapPreview;
    private bool _showingSourceHeatmap;
    private Process? _activeGenerationProcess;
    private Process? _activeTransferProcess;
    private DispatcherTimer? _generationPreviewTimer;
    private DispatcherTimer? _generationLogFlushTimer;
    private readonly ConcurrentQueue<string> _generationLogQueue = new();
    private string? _activeGenerationRunDir;
    private string? _activePreviewPath;
    private DateTime _activePreviewWriteUtc;
    private long _activePreviewLength;
    private string? _latestGenerationProgressLine;
    private DateTime _lastGenerationProgressLogUtc = DateTime.MinValue;
    private bool _seedLocked;
    private bool _seedOneShot;
    private bool _updatingSeedText;
    private bool _updatingJsonBrowser;
    private string? _selectedEditorProject;
    private bool _tutorialInitialized;

    public MainWindow()
    {
        InitializeComponent();
        _appRoot = ResolveAppRoot();
        _themes = BuildThemes();
        AppRootText.Text = _appRoot;

        ConfigureThemes();
        LoadShellSettings();
        LoadManualOverrideFieldsFromPreset();
        ApplyManualOverrideVisibility();
        UpdateFinalCheckpointsForSelectedLayers();
        UpdateSeedButtons();
        RefreshPreviewState();

        Log("KFPS WPF prototype started.");
        Log($"App root: {_appRoot}", updateStatus: false);
        StatusText.Text = "Ready";
        ShowView("Dashboard", DashboardView);
        CheckFirstLaunchSetup();

        if (Environment.GetCommandLineArgs().Any(arg => arg.Equals("--screenshot-all", StringComparison.OrdinalIgnoreCase)))
        {
            Loaded += (_, _) => Dispatcher.BeginInvoke(CaptureAllPagesAndClose, DispatcherPriority.ApplicationIdle);
        }
    }

    private string SettingsPath => Path.Combine(_appRoot, "runtime", "wpf-shell-settings.json");

    private static string ResolveAppRoot()
    {
        var starts = new[]
        {
            Path.GetDirectoryName(Environment.ProcessPath ?? string.Empty),
            Path.GetDirectoryName(Process.GetCurrentProcess().MainModule?.FileName ?? string.Empty),
            Directory.GetCurrentDirectory(),
            AppContext.BaseDirectory
        };

        foreach (var start in starts.Where(path => !string.IsNullOrWhiteSpace(path)).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var resolved = ResolveAppRootFrom(start!);
            if (resolved != null)
            {
                return resolved;
            }
        }

        return Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
    }

    private static string? ResolveAppRootFrom(string startPath)
    {
        var dir = new DirectoryInfo(startPath);
        while (dir != null)
        {
            var nestedAppRoot = Path.Combine(dir.FullName, "KloudysFH6Painter");
            if (IsKfpsAppRoot(nestedAppRoot))
            {
                return nestedAppRoot;
            }

            if (IsKfpsAppRoot(dir.FullName))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        return null;
    }

    private static bool IsKfpsAppRoot(string path)
    {
        return File.Exists(Path.Combine(path, "VERSION")) &&
               File.Exists(Path.Combine(path, "KloudysGalateaGenesis.exe"));
    }

    private void ConfigureThemes()
    {
        var wasLoading = _loadingSettings;
        _loadingSettings = true;
        ThemeComboBox.ItemsSource = _themes;
        ThemeComboBox.DisplayMemberPath = nameof(ThemeDefinition.Name);
        ThemeComboBox.SelectedIndex = 0;
        _loadingSettings = wasLoading;
    }

    private static List<ThemeDefinition> BuildThemes()
    {
        return
        [
            new ThemeDefinition(
                "Sakura Glass",
                "#FFFFFFFF", "#FFFFFBFD", "#FFFFF6F9",
                "#FF27212A", "#FF756A73", "#FFA1959D",
                "#FFFFFFFF", "#FFFFF9FB", "#FFFFEDF4", "#FFFFFFFF",
                "#FFFF6B9E", "#FFE9427F", "#55FF6B9E", "#FFE9D6DE"),
            new ThemeDefinition(
                "KFPS Modern",
                "#FF0B0F14", "#FF111821", "#FF16212D",
                "#FFEFF4F8", "#FF9DAAB7", "#FF697684",
                "#FF121820", "#FF18212C", "#FF202B38", "#FF0E141B",
                "#FF74D3FF", "#FF247BA0", "#5574D3FF", "#334C5B68"),
            new ThemeDefinition(
                "Blackout Neon",
                "#FF050507", "#FF0C0F12", "#FF15151D",
                "#FFF7F9FF", "#FFB4BAC7", "#FF727887",
                "#EE08090C", "#CC10131A", "#EE1A1F2B", "#FF0B0E14",
                "#FF60D5FF", "#FF1B6E9C", "#6660D5FF", "#55FFFFFF"),
            new ThemeDefinition(
                "Matrix Terminal",
                "#FF001207", "#FF001C0B", "#FF00280F",
                "#FFE6FFE8", "#FF9EE9AA", "#FF5BA566",
                "#EE001006", "#CC001A0A", "#EE003313", "#FF001508",
                "#FF52FF75", "#FF0F8F2C", "#6652FF75", "#6637FF5D"),
            new ThemeDefinition(
                "Arc Reactor Red",
                "#FF140303", "#FF2C0606", "#FF3E0D05",
                "#FFFFF5EA", "#FFE7C8A8", "#FF9F856B",
                "#EE1A0806", "#CC2A0A07", "#EE4A120B", "#FF200706",
                "#FFFFC35A", "#FFC23621", "#66FFCE7A", "#55FFDDA4"),
            new ThemeDefinition(
                "Deep Forge Blue",
                "#FF06111C", "#FF071B2A", "#FF102B42",
                "#FFF2FAFF", "#FFB6CEDD", "#FF728B9E",
                "#FF06101A", "#FF0C2031", "#FF143149", "#FF081722",
                "#FF8AC7FF", "#FF2D6594", "#668AC7FF", "#55C8E5FF"),
            new ThemeDefinition(
                "Windows Vista Aero",
                "#FF20354A", "#FF2D5575", "#FF162A3E",
                "#FFF4FAFF", "#FFC2D3E3", "#FF7C90A4",
                "#FF102131", "#FF18334B", "#FF244C6D", "#FF0D1B28",
                "#FF8ED9FF", "#FF2E7BC0", "#668ED9FF", "#55FFFFFF")
        ];
    }

    private void ThemeComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ThemeComboBox.SelectedItem is not ThemeDefinition theme)
        {
            return;
        }

        ApplyTheme(theme);
        if (!_loadingSettings)
        {
            SaveShellSettings();
            Log($"Theme applied: {theme.Name}");
        }
    }

    private void ApplyTheme(ThemeDefinition theme)
    {
        var resources = Application.Current.Resources;
        resources["InkBrush"] = Solid(theme.Ink);
        resources["MutedInkBrush"] = Solid(theme.MutedInk);
        resources["DimInkBrush"] = Solid(theme.DimInk);
        resources["PanelBrush"] = Solid(theme.Panel);
        resources["PanelSoftBrush"] = Solid(theme.PanelSoft);
        resources["PanelLiftBrush"] = Solid(theme.PanelLift);
        resources["ControlBrush"] = Solid(theme.Control);
        resources["AccentBrush"] = Solid(theme.Accent);
        resources["AccentDeepBrush"] = Solid(theme.AccentDeep);
        resources["AccentGlowBrush"] = Solid(theme.AccentGlow);
        resources["BorderBrushSoft"] = Solid(theme.Border);
        resources["AppBackgroundBrush"] = Gradient(theme.BackgroundA, theme.BackgroundB, theme.BackgroundC);
    }

    private static SolidColorBrush Solid(string color)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(color));
        brush.Freeze();
        return brush;
    }

    private static LinearGradientBrush Gradient(string a, string b, string c)
    {
        var brush = new LinearGradientBrush
        {
            StartPoint = new Point(0, 0),
            EndPoint = new Point(1, 1)
        };
        brush.GradientStops.Add(new GradientStop((Color)ColorConverter.ConvertFromString(a), 0));
        brush.GradientStops.Add(new GradientStop((Color)ColorConverter.ConvertFromString(b), 0.48));
        brush.GradientStops.Add(new GradientStop((Color)ColorConverter.ConvertFromString(c), 1));
        brush.Freeze();
        return brush;
    }

    private static string WithAlpha(string argbOrRgb, string alpha)
    {
        var value = argbOrRgb.TrimStart('#');
        if (value.Length == 8)
        {
            value = value[2..];
        }
        return "#" + alpha + value;
    }

    private void LoadShellSettings()
    {
        _loadingSettings = true;
        try
        {
            if (File.Exists(SettingsPath))
            {
                var settings = JsonSerializer.Deserialize<ShellSettings>(File.ReadAllText(SettingsPath));
                if (settings != null)
                {
                    var themeName = settings.ThemeName;
                    if (string.IsNullOrWhiteSpace(themeName) || themeName == "KFPS Modern")
                    {
                        themeName = "Sakura Glass";
                    }
                    var theme = _themes.FirstOrDefault(item => item.Name == themeName);
                    if (theme != null)
                    {
                        ThemeComboBox.SelectedItem = theme;
                    }

                    ManualOverridesCheckBox.IsChecked = settings.EnableManualOverrides;
                }
            }
        }
        catch (Exception ex)
        {
            Log($"Could not load WPF settings: {ex.Message}");
        }
        finally
        {
            _loadingSettings = false;
        }

        ApplyManualOverrideVisibility();
    }

    private void SaveShellSettings()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
            var settings = new ShellSettings
            {
                ThemeName = (ThemeComboBox.SelectedItem as ThemeDefinition)?.Name ?? _themes[0].Name,
                EnableManualOverrides = ManualOverridesCheckBox?.IsChecked == true
            };
            File.WriteAllText(SettingsPath, JsonSerializer.Serialize(settings, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception ex)
        {
            Log($"Could not save WPF settings: {ex.Message}");
        }
    }

    private void ShowDashboard(object sender, RoutedEventArgs e) => ShowView("Dashboard", DashboardView);
    private void ShowGenerate(object sender, RoutedEventArgs e) => ShowView("Generate", GenerateView);
    private void ShowImportExport(object sender, RoutedEventArgs e) => ShowView("Import / Export", ImportExportView);
    private void ShowEditor(object sender, RoutedEventArgs e) => ShowView("Editor", EditorView);
    private void ShowImageTools(object sender, RoutedEventArgs e) => ShowView("Image Tools", ImageToolsView);
    private void ShowTools(object sender, RoutedEventArgs e) => ShowView("Tools", ToolsView);
    private void ShowTutorial(object sender, RoutedEventArgs e) => ShowView("Help", TutorialView);
    private void ShowBugReports(object sender, RoutedEventArgs e) => ShowView("Bug Reports", BugReportsView);
    private void ShowSettings(object sender, RoutedEventArgs e) => ShowView("Settings", SettingsView);

    private void ShowView(string title, FrameworkElement view)
    {
        PageTitle.Text = title;
        (WorkflowKicker.Text, WorkflowTitle.Text) = title switch
        {
            "Dashboard" => ("OVERVIEW", "KFPS workspace"),
            "Generate" => ("CREATE", "Source and run controls"),
            "Import / Export" => ("TRANSFER", "JSON and game tools"),
            "Editor" => ("EDIT", "Launch and projects"),
            "Image Tools" => ("PREP", "Source checks"),
            "Tools" => ("TOOLS", "External helpers"),
            "Help" => ("LEARN", "Search topics"),
            "Bug Reports" => ("REPORT", "Write local report"),
            "Settings" => ("SYSTEM", "Checks and preferences"),
            _ => ("WORKFLOW", title)
        };
        foreach (var candidate in new[] { DashboardView, GenerateView, ImportExportView, EditorView, ImageToolsView, ToolsView, TutorialView, BugReportsView, SettingsView })
        {
            candidate.Visibility = candidate == view ? Visibility.Visible : Visibility.Collapsed;
        }

        var isDashboard = title == "Dashboard";
        WorkflowPanel.Visibility = isDashboard ? Visibility.Collapsed : Visibility.Visible;
        CenterHost.Visibility = isDashboard ? Visibility.Collapsed : Visibility.Visible;
        var usesWideWorkbench = isDashboard || title == "Generate" || title == "Import / Export" || title == "Editor" || title == "Image Tools" || title == "Tools" || title == "Help" || title == "Bug Reports" || title == "Settings";
        InspectorPanel.Visibility = usesWideWorkbench ? Visibility.Collapsed : Visibility.Visible;
        DashboardWideView.Visibility = isDashboard ? Visibility.Visible : Visibility.Collapsed;
        Grid.SetColumnSpan(CenterHost, title is "Generate" or "Import / Export" or "Editor" or "Image Tools" or "Tools" or "Help" or "Bug Reports" or "Settings" ? 2 : 1);

        var centerView = title switch
        {
            "Dashboard" => DashboardCenterView,
            "Generate" => GenerateCenterView,
            "Import / Export" => ImportExportCenterView,
            "Editor" => EditorCenterView,
            "Image Tools" => ImageToolsCenterView,
            "Tools" => ToolsCenterView,
            "Help" => TutorialCenterView,
            "Bug Reports" => BugReportsCenterView,
            "Settings" => SettingsCenterView,
            _ => GenerateCenterView
        };

        foreach (var candidate in new[] { DashboardCenterView, GenerateCenterView, ImportExportCenterView, EditorCenterView, ImageToolsCenterView, ToolsCenterView, TutorialCenterView, BugReportsCenterView, SettingsCenterView })
        {
            candidate.Visibility = candidate == centerView ? Visibility.Visible : Visibility.Collapsed;
        }

        if (title == "Import / Export")
        {
            PopulateJsonBrowser();
        }
        else if (title == "Editor")
        {
            PopulateEditorWorkspace();
        }
        else if (title == "Image Tools")
        {
            UpdateImageToolsPreviewAndReport();
        }
        else if (title == "Help")
        {
            InitializeTutorial();
        }
    }

    private void CaptureAllPagesAndClose()
    {
        try
        {
            var outputFolder = Path.Combine(_appRoot, "runtime", "wpf-screenshots", DateTime.Now.ToString("yyyyMMdd-HHmmss"));
            Directory.CreateDirectory(outputFolder);

            var pages = new (string Title, FrameworkElement View, string FileName)[]
            {
                ("Dashboard", DashboardView, "01-dashboard.png"),
                ("Generate", GenerateView, "02-generate.png"),
                ("Import / Export", ImportExportView, "03-import-export.png"),
                ("Editor", EditorView, "04-editor.png"),
                ("Image Tools", ImageToolsView, "05-image-tools.png"),
                ("Tools", ToolsView, "06-tools.png"),
                ("Help", TutorialView, "07-help.png"),
                ("Bug Reports", BugReportsView, "08-bug-reports.png"),
                ("Settings", SettingsView, "09-settings.png")
            };

            foreach (var page in pages)
            {
                ShowView(page.Title, page.View);
                UpdateLayout();
                CaptureWindowToPng(Path.Combine(outputFolder, page.FileName));
            }

            Log($"WPF screenshots written to: {outputFolder}");
        }
        catch (Exception ex)
        {
            Log($"Screenshot capture failed: {ex.Message}");
        }
        finally
        {
            Close();
        }
    }

    private void CaptureWindowToPng(string fileName)
    {
        var dpi = VisualTreeHelper.GetDpi(this);
        var width = Math.Max(1, (int)Math.Ceiling(ActualWidth * dpi.DpiScaleX));
        var height = Math.Max(1, (int)Math.Ceiling(ActualHeight * dpi.DpiScaleY));
        var bitmap = new RenderTargetBitmap(width, height, 96 * dpi.DpiScaleX, 96 * dpi.DpiScaleY, PixelFormats.Pbgra32);
        bitmap.Render(this);

        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var stream = File.Create(fileName);
        encoder.Save(stream);
    }

    private void ChooseSourceImage(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose source image",
            Filter = "Images|*.png;*.jpg;*.jpeg;*.webp;*.bmp|All files|*.*",
            InitialDirectory = GetStandaloneImagesFolder()
        };

        if (dialog.ShowDialog(this) == true)
        {
            _selectedSourceImage = dialog.FileName;
            _sourceHeatmapPreview = null;
            _showingSourceHeatmap = false;
            HeatmapToggleButton.Content = "Preview Heatmap";
            SetImage(SourcePreviewImage, SourcePreviewPlaceholder, dialog.FileName);
            SetImage(LatestPreviewImage, LatestPreviewPlaceholder, dialog.FileName);
            UpdateImageToolsPreviewAndReport(dialog.FileName);
            AutoSelectPresetForImage(dialog.FileName);
            Log($"Selected source image: {dialog.FileName}");
        }
    }

    private void ChooseJsonFile(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose vinyl JSON",
            Filter = "Vinyl JSON|*.json|All files|*.*"
        };

        if (dialog.ShowDialog(this) == true)
        {
            ImportManualJsonToExported(dialog.FileName);
        }
    }

    private void StartNativeGeneration(object sender, RoutedEventArgs e)
    {
        if (_activeGenerationProcess is { HasExited: false })
        {
            Log("Generation is already running.");
            return;
        }

        if (string.IsNullOrWhiteSpace(_selectedSourceImage) || !File.Exists(_selectedSourceImage))
        {
            Log("Choose a source image before generating.");
            return;
        }

        var bridge = Path.Combine(_appRoot, "KFPS.Wpf", "wpf_generate_bridge.py");
        if (!File.Exists(bridge))
        {
            Log($"Native generation bridge not found: {bridge}");
            return;
        }

        var python = ResolvePythonExecutable();
        if (python == null)
        {
            Log("Bundled Python was not found. Use Settings to check the bundle, then re-extract the package if needed.");
            CheckFirstLaunchSetup(forceVisibleOnFailure: true);
            return;
        }

        var layers = GetComboText(LayerComboBox, "2000");
        var saveAt = string.IsNullOrWhiteSpace(FinalCheckpointsTextBox.Text) ? layers : FinalCheckpointsTextBox.Text.Trim();
        var seed = EffectiveGenerationSeed();

        var args = new StringBuilder();
        args.Append("-u ");
        args.Append(Quote(bridge));
        args.Append(" --image ").Append(Quote(_selectedSourceImage));
        args.Append(" --preset-index ").Append(Math.Max(0, PresetComboBox.SelectedIndex));
        args.Append(" --layers ").Append(Quote(layers));
        args.Append(" --save-at ").Append(Quote(saveAt));
        args.Append(" --seed ").Append(seed);
        if (ManualOverridesCheckBox.IsChecked == true)
        {
            AppendOptionalArgument(args, "--max-resolution", ManualMaxResolutionTextBox.Text);
            AppendOptionalArgument(args, "--random-samples", ManualRandomSamplesTextBox.Text);
            AppendOptionalArgument(args, "--mutated-samples", ManualMutatedSamplesTextBox.Text);
        }
        if (LumaPrepCheckBox.IsChecked == true)
        {
            args.Append(" --luma-prep");
        }
        if (DetailHeatmapCheckBox.IsChecked == true)
        {
            args.Append(" --detail-heatmap");
        }
        if (EdgeRepairCheckBox.IsChecked == true)
        {
            args.Append(" --edge-repair");
        }
        if (SampleBoostCheckBox.IsChecked == true)
        {
            args.Append(" --sample-boost");
        }

        try
        {
            _activeGenerationRunDir = null;
            _activePreviewPath = null;
            _activePreviewWriteUtc = DateTime.MinValue;
            _activePreviewLength = 0;
            _latestGenerationProgressLine = null;
            ClearGenerationLogQueue();
            GenerateButton.IsEnabled = false;
            StopButton.IsEnabled = true;
            StatusText.Text = "Generating";
            Log($"Starting native generation for: {_selectedSourceImage}");
            StartGenerationLogFlushTimer();

            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = args.ToString(),
                WorkingDirectory = _appRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };

            var proc = new Process
            {
                StartInfo = startInfo,
                EnableRaisingEvents = true
            };
            proc.OutputDataReceived += (_, eventArgs) => HandleGenerationOutput(eventArgs.Data);
            proc.ErrorDataReceived += (_, eventArgs) => HandleGenerationOutput(eventArgs.Data);
            proc.Exited += (_, _) => Dispatcher.BeginInvoke(() =>
            {
                var exitCode = proc.ExitCode;
                StopGenerationPreviewTimer();
                StopGenerationLogFlushTimer(flushRemaining: true);
                RefreshActiveRunPreview();
                GenerateButton.IsEnabled = true;
                StopButton.IsEnabled = true;
                _activeGenerationProcess = null;
                StatusText.Text = exitCode == 0 ? "Done" : "Failed";
                Log(exitCode == 0 ? "Native generation finished." : $"Native generation exited with code {exitCode}.");
                proc.Dispose();
            });

            if (!proc.Start())
            {
                throw new InvalidOperationException("Process did not start.");
            }

            _activeGenerationProcess = proc;
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            StartGenerationPreviewTimer();
            ResetOneShotSeedAfterStart();
        }
        catch (Exception ex)
        {
            GenerateButton.IsEnabled = true;
            StopButton.IsEnabled = true;
            _activeGenerationProcess = null;
            StopGenerationLogFlushTimer(flushRemaining: true);
            Log($"Failed to start native generation: {ex.Message}");
        }
    }

    private static void AppendOptionalArgument(StringBuilder args, string option, string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return;
        }

        args.Append(' ').Append(option).Append(' ').Append(Quote(value.Trim()));
    }

    private void ManualOverridesChanged(object sender, RoutedEventArgs e)
    {
        ApplyManualOverrideVisibility();
        if (!_loadingSettings)
        {
            SaveShellSettings();
        }
    }

    private void ApplyManualOverrideVisibility()
    {
        if (ManualOverridesPanel == null || ManualOverridesCheckBox == null)
        {
            return;
        }

        var enabled = ManualOverridesCheckBox.IsChecked == true;
        ManualOverridesPanel.Visibility = enabled ? Visibility.Visible : Visibility.Collapsed;
        if (GenerateStatusCardsPanel != null)
        {
            GenerateStatusCardsPanel.Visibility = enabled ? Visibility.Collapsed : Visibility.Visible;
        }
        SampleBoostCheckBox.Visibility = Visibility.Visible;
    }

    private void PresetComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        LoadManualOverrideFieldsFromPreset();
    }

    private void LoadManualOverrideFieldsFromPreset()
    {
        if (PresetComboBox == null ||
            ManualMaxResolutionTextBox == null ||
            ManualRandomSamplesTextBox == null ||
            ManualMutatedSamplesTextBox == null ||
            string.IsNullOrWhiteSpace(_appRoot))
        {
            return;
        }

        var presetPath = PresetFileForIndex(Math.Max(0, PresetComboBox.SelectedIndex));
        var values = ReadPresetValues(presetPath);
        ManualMaxResolutionTextBox.Text = values.TryGetValue("maxResolution", out var maxResolution) ? maxResolution : "";
        ManualRandomSamplesTextBox.Text = values.TryGetValue("randomSamples", out var randomSamples) ? randomSamples : "";
        ManualMutatedSamplesTextBox.Text = values.TryGetValue("mutatedSamples", out var mutatedSamples) ? mutatedSamples : "";
    }

    private string PresetFileForIndex(int presetIndex)
    {
        var fileName = presetIndex switch
        {
            1 => "a.flat-colors.ini",
            2 => "c.gradients.ini",
            _ => "b.shaded-art.ini"
        };
        return Path.Combine(_appRoot, "settings", fileName);
    }

    private static Dictionary<string, string> ReadPresetValues(string presetPath)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            if (!File.Exists(presetPath))
            {
                return values;
            }

            foreach (var rawLine in File.ReadLines(presetPath))
            {
                var line = rawLine.Trim();
                if (line.Length == 0 || line.StartsWith('#') || !line.Contains('='))
                {
                    continue;
                }

                var splitAt = line.IndexOf('=');
                var key = line[..splitAt].Trim();
                var value = line[(splitAt + 1)..].Trim();
                if (key.Length > 0)
                {
                    values[key] = value;
                }
            }
        }
        catch
        {
            // Manual overrides are optional UI helpers; missing preset reads should not block launch.
        }

        return values;
    }

    private void StopNativeGeneration(object sender, RoutedEventArgs e)
    {
        var proc = _activeGenerationProcess;
        if (proc == null || proc.HasExited)
        {
            Log("No active generation job to stop.");
            return;
        }

        try
        {
            proc.Kill(entireProcessTree: true);
            Log("Generation stop requested.");
        }
        catch (Exception ex)
        {
            Log($"Failed to stop generation: {ex.Message}");
        }
    }

    private void HandleGenerationOutput(string? line)
    {
        if (string.IsNullOrWhiteSpace(line))
        {
            return;
        }

        Dispatcher.BeginInvoke(() =>
        {
            if (line.StartsWith("WPF_RUN_DIR:", StringComparison.OrdinalIgnoreCase))
            {
                _activeGenerationRunDir = line["WPF_RUN_DIR:".Length..].Trim();
                Log($"Run folder: {_activeGenerationRunDir}");
                return;
            }

            if (line.StartsWith("WPF_PREVIEW:", StringComparison.OrdinalIgnoreCase))
            {
                var preview = line["WPF_PREVIEW:".Length..].Trim();
                _activePreviewPath = preview;
                _activePreviewWriteUtc = DateTime.MinValue;
                _activePreviewLength = 0;
                SetImage(LatestPreviewImage, LatestPreviewPlaceholder, preview);
                Log($"Preview ready: {preview}");
                return;
            }

            EnqueueGenerationLog(line);
        });
    }

    private void EnqueueGenerationLog(string line)
    {
        if (TryCompactGenerationProgressLine(line, out var compactProgress))
        {
            _latestGenerationProgressLine = compactProgress;
            StatusText.Text = TrimStatus(compactProgress);
            return;
        }

        if (IsRoutineGenerationLine(line))
        {
            StatusText.Text = TrimStatus(line);
            return;
        }

        if (IsImportantGenerationLine(line))
        {
            _generationLogQueue.Enqueue(line);
            return;
        }

        StatusText.Text = TrimStatus(line);
    }

    private static bool TryCompactGenerationProgressLine(string line, out string compact)
    {
        compact = "";
        var completedIndex = line.IndexOf("Step completed in ", StringComparison.OrdinalIgnoreCase);
        if (completedIndex >= 0)
        {
            compact = line[completedIndex..].Trim();
            return true;
        }

        completedIndex = line.IndexOf("completed in ", StringComparison.OrdinalIgnoreCase);
        if (completedIndex >= 0)
        {
            compact = $"Step {line[completedIndex..].Trim()}";
            return true;
        }

        return false;
    }

    private static bool IsRoutineGenerationLine(string line)
    {
        return line.StartsWith("Building layer ", StringComparison.OrdinalIgnoreCase) ||
               line.StartsWith("Retry ", StringComparison.OrdinalIgnoreCase) ||
               line.StartsWith("Updated preview", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("Saved preview snapshot", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("candidate", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("score=", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("shape=", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("sample", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsImportantGenerationLine(string line)
    {
        return line.Contains("error", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("failed", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("exception", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("traceback", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("warning", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("final", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("complete", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("wrote", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("saved", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("output", StringComparison.OrdinalIgnoreCase) ||
               line.Contains("report", StringComparison.OrdinalIgnoreCase);
    }

    private static string TrimStatus(string text)
    {
        return text.Length > 110 ? text[..110] + "..." : text;
    }

    private void StartGenerationLogFlushTimer()
    {
        StopGenerationLogFlushTimer(flushRemaining: false);
        _generationLogFlushTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(250)
        };
        _generationLogFlushTimer.Tick += (_, _) => FlushGenerationLogQueue();
        _generationLogFlushTimer.Start();
    }

    private void StopGenerationLogFlushTimer(bool flushRemaining)
    {
        _generationLogFlushTimer?.Stop();
        _generationLogFlushTimer = null;
        if (flushRemaining)
        {
            FlushGenerationLogQueue(forceProgressLine: true);
        }
        _latestGenerationProgressLine = null;
    }

    private void ClearGenerationLogQueue()
    {
        while (_generationLogQueue.TryDequeue(out _))
        {
        }
    }

    private void FlushGenerationLogQueue(bool forceProgressLine = false)
    {
        var now = DateTime.UtcNow;
        if (!string.IsNullOrWhiteSpace(_latestGenerationProgressLine) &&
            (forceProgressLine || (now - _lastGenerationProgressLogUtc) >= TimeSpan.FromSeconds(2)))
        {
            Log(_latestGenerationProgressLine);
            _lastGenerationProgressLogUtc = now;
            _latestGenerationProgressLine = null;
        }

        var drained = 0;
        while (drained < 40 && _generationLogQueue.TryDequeue(out var line))
        {
            Log(line);
            drained++;
        }

        if (!_generationLogQueue.IsEmpty)
        {
            StatusText.Text = "Generation is running; log output is being throttled to keep the UI responsive.";
        }
    }

    private void StartGenerationPreviewTimer()
    {
        StopGenerationPreviewTimer();
        _generationPreviewTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(1)
        };
        _generationPreviewTimer.Tick += (_, _) => RefreshActiveRunPreview();
        _generationPreviewTimer.Start();
    }

    private void StopGenerationPreviewTimer()
    {
        _generationPreviewTimer?.Stop();
        _generationPreviewTimer = null;
    }

    private void RefreshActiveRunPreview()
    {
        var preview = FindNewestPreviewInRun(_activeGenerationRunDir);
        if (preview != null && ShouldReloadActivePreview(preview))
        {
            SetImage(LatestPreviewImage, LatestPreviewPlaceholder, preview);
        }
    }

    private bool ShouldReloadActivePreview(string preview)
    {
        try
        {
            var info = new FileInfo(preview);
            if (!info.Exists)
            {
                return false;
            }

            var writeUtc = info.LastWriteTimeUtc;
            var length = info.Length;
            if (string.Equals(_activePreviewPath, preview, StringComparison.OrdinalIgnoreCase) &&
                _activePreviewWriteUtc == writeUtc &&
                _activePreviewLength == length)
            {
                return false;
            }

            _activePreviewPath = preview;
            _activePreviewWriteUtc = writeUtc;
            _activePreviewLength = length;
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void SelectJson(string fileName)
    {
        try
        {
            var fullPath = Path.GetFullPath(fileName);
            if (!File.Exists(fullPath))
            {
                Log($"Selected JSON no longer exists: {fileName}");
                return;
            }

            _selectedJson = fullPath;
            SelectedJsonText.Text = fullPath;
            var preview = FindPreviewForJson(fullPath) ?? RenderJsonPreviewFallback(fullPath);
            if (preview != null)
            {
                SetImage(LatestPreviewImage, LatestPreviewPlaceholder, preview);
                SetImage(JsonPreviewImage, JsonPreviewPlaceholder, preview);
            }
            else if (JsonPreviewImage != null)
            {
                JsonPreviewImage.Source = null;
                JsonPreviewPlaceholder.Visibility = Visibility.Visible;
            }
            UpdateJsonDetails(fullPath);
            Log($"Selected JSON: {fullPath}");
        }
        catch (Exception ex)
        {
            _selectedJson = fileName;
            SelectedJsonText.Text = fileName;
            JsonPreviewImage.Source = null;
            JsonPreviewPlaceholder.Visibility = Visibility.Visible;
            UpdateJsonDetails(fileName);
            Log($"Selected JSON without preview: {fileName} ({ex.Message})");
        }
    }

    private void StartNativeImport(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_selectedJson) || !File.Exists(_selectedJson))
        {
            Log("Choose a JSON before importing.");
            return;
        }

        if (!TryGetTransferLayerCount(out var layerCount))
        {
            return;
        }

        var args = new StringBuilder("import");
        args.Append(" --game ").Append(GetSelectedTransferGame());
        args.Append(" --layer-count ").Append(layerCount);
        args.Append(" --json ").Append(Quote(_selectedJson));
        if (TransferClearUnusedCheckBox.IsChecked == true)
        {
            args.Append(" --clear-unused");
        }

        StartNativeTransfer(args.ToString(), "Importing JSON into game...");
    }

    private void StartNativeExport(object sender, RoutedEventArgs e)
    {
        if (!TryGetTransferLayerCount(out var layerCount))
        {
            return;
        }

        var args = new StringBuilder("export");
        args.Append(" --game ").Append(GetSelectedTransferGame());
        args.Append(" --layer-count ").Append(layerCount);
        StartNativeTransfer(args.ToString(), "Exporting current game group...");
    }

    private void StartNativeTransfer(string bridgeArguments, string status)
    {
        if (_activeTransferProcess is { HasExited: false })
        {
            Log("A transfer job is already running.");
            return;
        }

        var bridge = Path.Combine(_appRoot, "KFPS.Wpf", "wpf_transfer_bridge.py");
        if (!File.Exists(bridge))
        {
            Log($"Native transfer bridge not found: {bridge}");
            return;
        }

        var python = ResolvePythonExecutable();
        if (python == null)
        {
            Log("Import/export needs the bundled Python runtime. Check the bundle in Settings.");
            CheckFirstLaunchSetup(forceVisibleOnFailure: true);
            return;
        }

        try
        {
            ImportJsonButton.IsEnabled = false;
            ExportJsonButton.IsEnabled = false;
            StatusText.Text = status;
            Log(status);

            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = $"-u {Quote(bridge)} {bridgeArguments}",
                WorkingDirectory = _appRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };

            var proc = new Process
            {
                StartInfo = startInfo,
                EnableRaisingEvents = true
            };
            proc.OutputDataReceived += (_, eventArgs) => HandleTransferOutput(eventArgs.Data);
            proc.ErrorDataReceived += (_, eventArgs) => HandleTransferOutput(eventArgs.Data);
            proc.Exited += (_, _) => Dispatcher.BeginInvoke(() =>
            {
                var exitCode = proc.ExitCode;
                ImportJsonButton.IsEnabled = true;
                ExportJsonButton.IsEnabled = true;
                _activeTransferProcess = null;
                StatusText.Text = exitCode == 0 ? "Done" : "Failed";
                Log(exitCode == 0 ? "Native transfer finished." : $"Native transfer exited with code {exitCode}.");
                PopulateJsonBrowser();
                PopulateEditorWorkspace();
                proc.Dispose();
            });

            if (!proc.Start())
            {
                throw new InvalidOperationException("Process did not start.");
            }

            _activeTransferProcess = proc;
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
        }
        catch (Exception ex)
        {
            ImportJsonButton.IsEnabled = true;
            ExportJsonButton.IsEnabled = true;
            _activeTransferProcess = null;
            Log($"Failed to start native transfer: {ex.Message}");
        }
    }

    private void HandleTransferOutput(string? line)
    {
        if (string.IsNullOrWhiteSpace(line))
        {
            return;
        }

        Dispatcher.BeginInvoke(() =>
        {
            if (line.StartsWith("WPF_SELECTED_JSON:", StringComparison.OrdinalIgnoreCase))
            {
                var path = line["WPF_SELECTED_JSON:".Length..].Trim();
                if (File.Exists(path))
                {
                    JsonSourceComboBox.SelectedIndex = IsUnderPath(path, Path.Combine(_appRoot, "imgs", "editor")) ? 1 : 2;
                    SelectJson(path);
                }
                return;
            }

            Log(line);
        });
    }

    private string GetSelectedTransferGame()
    {
        if (TransferGameComboBox.SelectedItem is ComboBoxItem item)
        {
            var value = item.Content?.ToString()?.Trim().ToLowerInvariant() ?? "fh6";
            return value.StartsWith("fm8", StringComparison.OrdinalIgnoreCase) ? "fm8" : value;
        }

        return "fh6";
    }

    private bool TryGetTransferLayerCount(out int layerCount)
    {
        layerCount = 0;
        if (!int.TryParse(TransferLayerCountTextBox.Text.Trim(), out layerCount) || layerCount <= 0 || layerCount > 3000)
        {
            Log("Loaded template/group layer count must be a number from 1 to 3000.");
            return false;
        }

        return true;
    }

    private void RefreshPreviews(object sender, RoutedEventArgs e) => RefreshPreviewState();
    private void RefreshImageReport(object sender, RoutedEventArgs e) => RefreshPreviewState();

    private void RefreshJsonBrowser(object sender, RoutedEventArgs e) => PopulateJsonBrowser();

    private void JsonSourceComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_updatingJsonBrowser || JsonGroupList == null)
        {
            return;
        }

        ClearSelectedJson();
        PopulateJsonBrowser();
    }

    private void JsonGroupList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_updatingJsonBrowser || JsonFileList == null)
        {
            return;
        }

        if (JsonGroupList.SelectedItem is not JsonBrowserGroup group)
        {
            JsonFileList.ItemsSource = null;
            JsonListTitle.Text = "Checkpoint JSONs";
            return;
        }

        OpenJsonGroup(group);
    }

    private void JsonGroupList_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (_updatingJsonBrowser || JsonGroupList == null || JsonFileList == null)
        {
            return;
        }

        var item = ItemsControl.ContainerFromElement(JsonGroupList, e.OriginalSource as DependencyObject) as ListBoxItem;
        if (item?.DataContext is not JsonBrowserGroup group)
        {
            return;
        }

        JsonGroupList.SelectedItem = group;
        OpenJsonGroup(group);
        e.Handled = true;
    }

    private void JsonGroupButton_Click(object sender, RoutedEventArgs e)
    {
        if (_updatingJsonBrowser || JsonGroupList == null || JsonFileList == null)
        {
            return;
        }

        if ((sender as FrameworkElement)?.DataContext is not JsonBrowserGroup group)
        {
            return;
        }

        JsonGroupList.SelectedItem = group;
        OpenJsonGroup(group);
        JsonBrowserStatusText.Text = $"Opened {group.Name}. Choose a checkpoint JSON.";
    }

    private void OpenJsonGroup(JsonBrowserGroup group)
    {
        if (JsonFileList == null)
        {
            return;
        }

        var source = GetSelectedJsonSource();
        var files = group.JsonFiles
            .Where(file => !source.IsGenerated || IsV2CheckpointJson(file.FullPath))
            .OrderByDescending(file => file.Modified)
            .ToList();

        JsonFileList.ItemsSource = files;
        JsonFileList.SelectedItem = null;
        JsonListTitle.Text = source.IsGenerated
            ? $"V2 checkpoint JSONs ({files.Count})"
            : $"Checkpoint JSONs ({files.Count})";
        JsonBrowserStatusText.Text = files.Count == 0
            ? "No JSONs found in the selected folder."
            : $"Opened {group.Name}. Choose a checkpoint JSON.";
    }

    private static bool IsV2CheckpointJson(string path)
    {
        var name = Path.GetFileNameWithoutExtension(path);
        return name.Contains("v2", StringComparison.OrdinalIgnoreCase);
    }

    private void JsonFileList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        // File selection is handled by the row click so clicking the selected
        // JSON again can reliably toggle it off instead of immediately reselecting.
    }

    private void JsonFileItem_MouseLeftButtonUp(object sender, MouseButtonEventArgs e)
    {
        if (_updatingJsonBrowser)
        {
            return;
        }

        if ((sender as FrameworkElement)?.DataContext is not JsonBrowserFile file)
        {
            return;
        }

        ActivateJsonBrowserFile(file, allowToggle: true);
        e.Handled = true;
    }

    private void JsonFileList_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (_updatingJsonBrowser || JsonFileList == null)
        {
            return;
        }

        var item = ItemsControl.ContainerFromElement(JsonFileList, e.OriginalSource as DependencyObject) as ListBoxItem;
        if (item?.DataContext is not JsonBrowserFile file)
        {
            return;
        }

        ActivateJsonBrowserFile(file, allowToggle: true);
        e.Handled = true;
    }

    private void JsonFileButton_Click(object sender, RoutedEventArgs e)
    {
        if (_updatingJsonBrowser)
        {
            return;
        }

        if ((sender as FrameworkElement)?.DataContext is not JsonBrowserFile file)
        {
            return;
        }

        ActivateJsonBrowserFile(file, allowToggle: true);
    }

    private void ActivateJsonBrowserFile(JsonBrowserFile file, bool allowToggle)
    {
        if (string.Equals(_selectedJson, file.FullPath, StringComparison.OrdinalIgnoreCase))
        {
            if (!allowToggle)
            {
                return;
            }

            ClearSelectedJson();
            if (JsonFileList != null)
            {
                JsonFileList.SelectedItem = null;
            }
            JsonBrowserStatusText.Text = $"Cleared selection: {file.Name}";
            Log($"Cleared selected JSON: {file.FullPath}");
            return;
        }

        SelectJsonInBrowser(file.FullPath);
        SelectJson(file.FullPath);
        JsonBrowserStatusText.Text = $"Ready to import: {file.Name}";
    }

    private void ImportManualJsonToExported(string sourceFile)
    {
        try
        {
            if (!File.Exists(sourceFile))
            {
                Log($"Manual JSON does not exist: {sourceFile}");
                return;
            }

            var exportedRoot = Path.Combine(_appRoot, "imgs", "exported");
            Directory.CreateDirectory(exportedRoot);
            var destination = UniqueFilePath(exportedRoot, Path.GetFileName(sourceFile));
            File.Copy(sourceFile, destination, overwrite: false);

            JsonSourceComboBox.SelectedIndex = 2;
            PopulateJsonBrowser();
            SelectJson(destination);
            SelectJsonInBrowser(destination);
            JsonBrowserStatusText.Text = $"Copied to Exported and selected: {Path.GetFileName(destination)}";
            Log($"Manual JSON copied to Exported: {destination}");
        }
        catch (Exception ex)
        {
            Log($"Manual JSON import failed: {ex.Message}");
            SelectJson(sourceFile);
        }
    }

    private static string UniqueFilePath(string folder, string fileName)
    {
        var safeName = string.IsNullOrWhiteSpace(fileName) ? "manual.json" : SanitizeFilePart(fileName);
        if (!safeName.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
        {
            safeName += ".json";
        }

        var stem = Path.GetFileNameWithoutExtension(safeName);
        var extension = Path.GetExtension(safeName);
        var candidate = Path.Combine(folder, safeName);
        var index = 2;
        while (File.Exists(candidate))
        {
            candidate = Path.Combine(folder, $"{stem} ({index}){extension}");
            index++;
        }

        return candidate;
    }

    private void SelectJsonInBrowser(string jsonPath)
    {
        if (JsonGroupList?.ItemsSource is not IEnumerable<JsonBrowserGroup> groups || JsonFileList == null)
        {
            return;
        }

        foreach (var group in groups)
        {
            var file = group.JsonFiles.FirstOrDefault(item => string.Equals(item.FullPath, jsonPath, StringComparison.OrdinalIgnoreCase));
            if (file == null)
            {
                continue;
            }

            JsonGroupList.SelectedItem = group;
            var files = group.JsonFiles.OrderByDescending(item => item.Modified).ToList();
            JsonFileList.ItemsSource = files;
            JsonFileList.SelectedItem = files.FirstOrDefault(item => string.Equals(item.FullPath, jsonPath, StringComparison.OrdinalIgnoreCase));
            return;
        }
    }

    private void ClearSelectedJson()
    {
        _selectedJson = null;
        SelectedJsonText.Text = "No JSON selected yet.";
        if (JsonPreviewImage != null)
        {
            JsonPreviewImage.Source = null;
            JsonPreviewPlaceholder.Visibility = Visibility.Visible;
        }
        JsonDetailNameText.Text = "Name: -";
        JsonDetailLayerText.Text = "Layers: -";
        JsonDetailFolderText.Text = "Folder: -";
    }

    private void PopulateJsonBrowser()
    {
        if (JsonSourceComboBox == null || JsonGroupList == null || JsonFileList == null)
        {
            return;
        }

        _updatingJsonBrowser = true;
        try
        {
            var source = GetSelectedJsonSource();
            JsonGroupTitle.Text = source.GroupTitle;
            JsonListTitle.Text = "Checkpoint JSONs";
            JsonFileList.ItemsSource = null;
            JsonPreviewImage.Source = null;
            JsonPreviewPlaceholder.Visibility = Visibility.Visible;
            JsonDetailNameText.Text = "Name: -";
            JsonDetailLayerText.Text = "Layers: -";
            JsonDetailFolderText.Text = "Folder: -";

            Directory.CreateDirectory(source.Root);
            var groups = BuildJsonBrowserGroups(source.Root, source.IsGenerated)
                .OrderByDescending(group => group.Modified)
                .ToList();

            JsonGroupList.ItemsSource = groups;
            JsonBrowserStatusText.Text = groups.Count == 0
                ? $"No JSONs found in {source.Root}."
                : $"{groups.Count} generation/folder group(s) found in {source.Root}.";

            if (groups.Count > 0)
            {
                JsonGroupList.SelectedIndex = 0;
            }
        }
        finally
        {
            _updatingJsonBrowser = false;
        }

        JsonGroupList_SelectionChanged(JsonGroupList, new SelectionChangedEventArgs(Selector.SelectionChangedEvent, Array.Empty<object>(), Array.Empty<object>()));
    }

    private JsonSourceDefinition GetSelectedJsonSource()
    {
        var index = JsonSourceComboBox?.SelectedIndex ?? 0;
        return index switch
        {
            1 => new JsonSourceDefinition("Editor exports", "Editor folders", Path.Combine(_appRoot, "imgs", "editor"), false),
            2 => new JsonSourceDefinition("Exported game JSONs", "Export folders", Path.Combine(_appRoot, "imgs", "exported"), false),
            _ => new JsonSourceDefinition("Generated finals", "Generations", Path.Combine(_appRoot, "imgs", "generated"), true)
        };
    }

    private static List<JsonBrowserGroup> BuildJsonBrowserGroups(string root, bool generated)
    {
        if (!Directory.Exists(root))
        {
            return [];
        }

        if (generated)
        {
            var generationFolders = Directory.EnumerateDirectories(root)
                .Select(folder => BuildGroupFromFolder(folder, Path.GetFileName(folder), generated: true))
                .Where(group => group.JsonFiles.Count > 0)
                .ToList();

            if (generationFolders.Count > 0)
            {
                return generationFolders;
            }
        }

        var files = Directory.EnumerateFiles(root, "*.json", SearchOption.AllDirectories)
            .Where(IsImportableJsonCandidate)
            .Select(path => new JsonBrowserFile(path, Path.GetFileName(path), Directory.GetLastWriteTime(path)))
            .GroupBy(file => Path.GetDirectoryName(file.FullPath) ?? root)
            .Select(group =>
            {
                var folder = group.Key;
                var name = string.Equals(folder, root, StringComparison.OrdinalIgnoreCase)
                    ? Path.GetFileName(root)
                    : Path.GetRelativePath(root, folder);
                var filesInGroup = group.OrderByDescending(file => file.Modified).ToList();
                return new JsonBrowserGroup(name, folder, filesInGroup, filesInGroup.Max(file => file.Modified));
            })
            .ToList();

        return files;
    }

    private static JsonBrowserGroup BuildGroupFromFolder(string folder, string name, bool generated = false)
    {
        var files = Directory.EnumerateFiles(folder, "*.json", SearchOption.AllDirectories)
            .Where(IsImportableJsonCandidate)
            .Where(path => !generated || IsV2CheckpointJson(path))
            .Select(path => new JsonBrowserFile(path, Path.GetFileName(path), Directory.GetLastWriteTime(path)))
            .OrderByDescending(file => file.Modified)
            .ToList();
        var modified = files.Count > 0 ? files.Max(file => file.Modified) : Directory.GetLastWriteTime(folder);
        return new JsonBrowserGroup(name, folder, files, modified);
    }

    private static bool IsImportableJsonCandidate(string path)
    {
        var name = Path.GetFileName(path);
        var lower = name.ToLowerInvariant();
        if (lower.EndsWith(".report.json", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var blockedParts = new[]
        {
            ".settings.",
            "settings",
            "metadata",
            "backup",
            "session",
            "probe",
            "report",
            "manifest"
        };

        return !blockedParts.Any(part => lower.Contains(part, StringComparison.OrdinalIgnoreCase));
    }

    private void UpdateJsonDetails(string fileName)
    {
        if (JsonDetailNameText == null)
        {
            return;
        }

        JsonDetailNameText.Text = $"Name: {Path.GetFileName(fileName)}";
        JsonDetailFolderText.Text = $"Folder: {Path.GetDirectoryName(fileName)}";
        JsonDetailLayerText.Text = $"Layers: {CountJsonLayers(fileName)?.ToString() ?? "unknown"}";
    }

    private void RefreshEditorWorkspace(object sender, RoutedEventArgs e) => PopulateEditorWorkspace();

    private void PopulateEditorWorkspace()
    {
        if (EditorProjectList == null)
        {
            return;
        }

        var projectRoot = EditorProjectRoot();
        Directory.CreateDirectory(projectRoot);

        var projects = BuildEditorProjects(projectRoot);

        EditorProjectList.ItemsSource = projects;
        EditorWorkspaceStatusText.Text = $"{projects.Count} project file(s) found.";

        if (projects.Count > 0)
        {
            EditorProjectList.SelectedIndex = 0;
        }
        else
        {
            _selectedEditorProject = null;
            EditorDetailNameText.Text = "Name: -";
            EditorDetailLayerText.Text = "Shapes: -";
            EditorDetailFolderText.Text = "File: -";
        }
    }

    private static List<EditorProjectItem> BuildEditorProjects(string projectRoot)
    {
        if (!Directory.Exists(projectRoot))
        {
            return [];
        }

        var files = Directory.EnumerateFiles(projectRoot, "*.fabric-project.json", SearchOption.AllDirectories)
            .Select(path => new EditorProjectItem(Path.GetFileName(path), path, Directory.GetLastWriteTime(path), false))
            .ToList();

        return files
            .OrderByDescending(item => item.Modified)
            .ToList();
    }

    private void EditorProjectList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (EditorProjectList.SelectedItem is not EditorProjectItem item)
        {
            return;
        }

        _selectedEditorProject = item.FullPath;
        EditorDetailNameText.Text = $"Name: {ProjectDisplayName(item.FullPath)}";
        EditorDetailLayerText.Text = $"Shapes: {CountJsonLayers(item.FullPath)?.ToString() ?? "unknown"}";
        EditorDetailFolderText.Text = $"File: {item.FullPath}";
        var preview = FindPreviewForJson(item.FullPath) ?? RenderJsonPreviewFallback(item.FullPath);
        if (preview != null)
        {
            SetImage(EditorProjectPreviewImage, EditorProjectPreviewPlaceholder, preview);
        }
        else
        {
            EditorProjectPreviewImage.Source = null;
            EditorProjectPreviewPlaceholder.Visibility = Visibility.Visible;
        }
        EditorWorkspaceStatusText.Text = $"Selected project: {Path.GetFileName(item.FullPath)}";
    }

    private void UseSelectedProjectInEditor(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_selectedEditorProject) || !File.Exists(_selectedEditorProject))
        {
            Log("No editor project selected.");
            return;
        }

        StartFabricEditorWithProject(_selectedEditorProject);
    }

    private string EditorProjectRoot() => Path.Combine(_appRoot, "runtime", "fabric-editor", "projects");

    private static string ProjectDisplayName(string path)
    {
        var name = Path.GetFileName(path);
        return name.EndsWith(".fabric-project.json", StringComparison.OrdinalIgnoreCase)
            ? name[..^".fabric-project.json".Length]
            : Path.GetFileNameWithoutExtension(path);
    }

    private static int? CountJsonLayers(string fileName)
    {
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(fileName));
            var root = doc.RootElement;
            if (root.ValueKind == JsonValueKind.Array)
            {
                return root.GetArrayLength();
            }

            foreach (var key in new[] { "shapes", "layers", "items" })
            {
                if (root.TryGetProperty(key, out var property) && property.ValueKind == JsonValueKind.Array)
                {
                    return property.GetArrayLength();
                }
            }
        }
        catch
        {
            return null;
        }

        return null;
    }

    private void ToggleHeatmapPreview(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_selectedSourceImage) || !File.Exists(_selectedSourceImage))
        {
            Log("Choose a source image before previewing its heatmap.");
            return;
        }

        try
        {
            if (_showingSourceHeatmap)
            {
                SetImage(LatestPreviewImage, LatestPreviewPlaceholder, _selectedSourceImage);
                _showingSourceHeatmap = false;
                HeatmapToggleButton.Content = "Preview Heatmap";
                Log("Showing source image preview.");
                return;
            }

            _sourceHeatmapPreview ??= CreateSourceHeatmapPreview(_selectedSourceImage);
            SetImage(LatestPreviewImage, LatestPreviewPlaceholder, _sourceHeatmapPreview);
            _showingSourceHeatmap = true;
            HeatmapToggleButton.Content = "Show Source";
            Log("Showing source detail heatmap preview.");
        }
        catch (Exception ex)
        {
            Log($"Heatmap preview failed: {ex.Message}");
        }
    }

    private void RefreshPreviewState()
    {
        if (!string.IsNullOrWhiteSpace(_selectedSourceImage) && File.Exists(_selectedSourceImage))
        {
            SetImage(SourcePreviewImage, SourcePreviewPlaceholder, _selectedSourceImage);
        }

        UpdateImageToolsPreviewAndReport();
        PopulateRecentFiles();
        Log("Preview rail refreshed.");
    }

    private void UpdateImageToolsPreviewAndReport(string? imagePath = null)
    {
        imagePath ??= _selectedSourceImage;

        var preview = FindControl<Image>("ImageToolsPreviewImage");
        var placeholder = FindControl<TextBlock>("ImageToolsPreviewPlaceholder");
        var report = FindControl<TextBlock>("ImageToolsReportText");
        var sourceCheckBorder = FindControl<Border>("ImageToolsSourceCheckBorder");
        var sourceCheckText = FindControl<TextBlock>("ImageToolsSourceCheckText");

        if (string.IsNullOrWhiteSpace(imagePath) || !File.Exists(imagePath))
        {
            if (preview != null)
            {
                preview.Source = null;
            }

            if (placeholder != null)
            {
                placeholder.Text = "Choose an image from the left panel to preview it here.";
                placeholder.Visibility = Visibility.Visible;
            }

            if (report != null)
            {
                report.Text = "No source image selected.";
            }

            SetSourceCheck(sourceCheckBorder, sourceCheckText, "neutral", "Choose an image to get a source check.");
            return;
        }

        if (preview != null && placeholder != null)
        {
            SetImage(preview, placeholder, imagePath);
        }

        if (report != null)
        {
            var sourceReport = BuildSourceImageReport(imagePath);
            report.Text = sourceReport.Metrics;
            SetSourceCheck(sourceCheckBorder, sourceCheckText, sourceReport.Severity, sourceReport.SourceCheck);
        }
    }

    private ImageSourceReport BuildSourceImageReport(string imagePath)
    {
        try
        {
            var info = new FileInfo(imagePath);
            var decoder = BitmapDecoder.Create(new Uri(imagePath, UriKind.Absolute), BitmapCreateOptions.IgnoreColorProfile, BitmapCacheOption.OnLoad);
            var frame = decoder.Frames[0];
            var width = frame.PixelWidth;
            var height = frame.PixelHeight;
            var megapixels = width * height / 1_000_000.0;
            var alphaReport = EstimateTransparency(frame);
            var (severity, sizeAdvice) = megapixels switch
            {
                < 0.45 => ("red", "Very small source. Upscale or use cleaner art before generating."),
                < 0.8 => ("yellow", "Small source. Usable, but fine details may be weak."),
                > 10.0 => ("red", "Very large source. Downscale first to avoid wasted time and noisy detail."),
                > 6.0 => ("yellow", "Large source. Usually worth resizing unless the detail is intentional."),
                _ => ("green", "Source size is in a practical range.")
            };

            var metrics =
                $"File: {Path.GetFileName(imagePath)}\n" +
                $"Resolution: {width} x {height}\n" +
                $"Megapixels: {megapixels:0.00} MP\n" +
                $"File size: {FormatBytes(info.Length)}\n" +
                $"Transparency: {alphaReport}";
            return new ImageSourceReport(metrics, sizeAdvice, severity);
        }
        catch (Exception ex)
        {
            return new ImageSourceReport("Could not read image report.", ex.Message, "red");
        }
    }

    private static void SetSourceCheck(Border? border, TextBlock? text, string severity, string message)
    {
        if (text != null)
        {
            text.Text = message;
        }

        if (border == null)
        {
            return;
        }

        var (background, outline) = severity switch
        {
            "green" => ("#FFE9FBEF", "#FF35A852"),
            "yellow" => ("#FFFFF7D6", "#FFE5A100"),
            "red" => ("#FFFFE7E7", "#FFE14444"),
            _ => ("#FFF3F4F6", "#FFCBD5E1")
        };

        border.Background = (Brush)new BrushConverter().ConvertFromString(background)!;
        border.BorderBrush = (Brush)new BrushConverter().ConvertFromString(outline)!;
    }

    private sealed record ImageSourceReport(string Metrics, string SourceCheck, string Severity);

    private static string EstimateTransparency(BitmapSource source)
    {
        var converted = new FormatConvertedBitmap(source, PixelFormats.Bgra32, null, 0);
        converted.Freeze();

        var scale = Math.Min(1.0, 180.0 / Math.Max(converted.PixelWidth, converted.PixelHeight));
        BitmapSource sample = converted;
        if (scale < 1.0)
        {
            sample = new TransformedBitmap(converted, new ScaleTransform(scale, scale));
            sample.Freeze();
        }

        var width = Math.Max(1, sample.PixelWidth);
        var height = Math.Max(1, sample.PixelHeight);
        var stride = width * 4;
        var pixels = new byte[stride * height];
        sample.CopyPixels(pixels, stride, 0);

        var transparent = 0;
        var semi = 0;
        var opaque = 0;

        for (var index = 3; index < pixels.Length; index += 4)
        {
            var alpha = pixels[index];
            if (alpha < 8)
            {
                transparent++;
            }
            else if (alpha < 248)
            {
                semi++;
            }
            else
            {
                opaque++;
            }
        }

        var total = Math.Max(1, transparent + semi + opaque);
        var transparentPercent = transparent * 100.0 / total;
        var semiPercent = semi * 100.0 / total;
        var visiblePercent = (semi + opaque) * 100.0 / total;

        if (transparentPercent < 0.2 && semiPercent < 0.2)
        {
            return "Opaque or no meaningful alpha.";
        }

        return $"{visiblePercent:0.#}% visible, {transparentPercent:0.#}% transparent, {semiPercent:0.#}% soft-edge alpha.";
    }

    private static string FormatBytes(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB"];
        var size = (double)Math.Max(0, bytes);
        var unit = 0;
        while (size >= 1024 && unit < units.Length - 1)
        {
            size /= 1024;
            unit++;
        }

        return $"{size:0.#} {units[unit]}";
    }

    private void PopulateRecentFiles()
    {
        var roots = new[]
        {
            Path.Combine(_appRoot, "imgs", "generated"),
            Path.Combine(_appRoot, "imgs", "editor"),
            Path.Combine(_appRoot, "imgs", "exported")
        };

        var items = roots
            .Where(Directory.Exists)
            .SelectMany(root => Directory.EnumerateFiles(root, "*.*", SearchOption.AllDirectories))
            .Where(path => path.EndsWith(".json", StringComparison.OrdinalIgnoreCase) ||
                           path.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
            .Select(path => new RecentFileItem(path, Path.GetFileName(path), Directory.GetLastWriteTime(path)))
            .OrderByDescending(item => item.Modified)
            .Take(80)
            .ToList();

        RecentFilesList.ItemsSource = items;
    }

    private void RecentFilesList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (RecentFilesList.SelectedItem is not RecentFileItem item)
        {
            return;
        }

        if (item.Path.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
        {
            SelectJson(item.Path);
            return;
        }

        if (item.Path.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
        {
            SetImage(LatestPreviewImage, LatestPreviewPlaceholder, item.Path);
            Log($"Preview selected: {item.Path}");
        }
    }

    private string? FindLatestGeneratedPreview()
    {
        var generatedRoot = Path.Combine(_appRoot, "imgs", "generated");
        if (!Directory.Exists(generatedRoot))
        {
            return null;
        }

        return Directory.EnumerateFiles(generatedRoot, "*.png", SearchOption.AllDirectories)
            .Where(path => path.Contains($"{Path.DirectorySeparatorChar}previews{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase) ||
                           path.Contains($"{Path.DirectorySeparatorChar}finals{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(File.GetLastWriteTime)
            .FirstOrDefault();
    }

    private string? FindPreviewForJson(string jsonPath)
    {
        try
        {
            var path = Path.GetFullPath(jsonPath);
            var name = Path.GetFileNameWithoutExtension(path);
            var previewNames = BuildPreviewNameCandidates(name);
            var parent = Path.GetDirectoryName(path);
            if (parent == null || !Directory.Exists(parent))
            {
                return null;
            }

            var direct = FindMatchingPreview(parent, previewNames, recursive: false);
            if (direct != null)
            {
                return direct;
            }

            var runRoot = new DirectoryInfo(parent).Parent?.FullName;
            var imgsRoot = Path.Combine(_appRoot, "imgs");
            if (runRoot != null && Directory.Exists(runRoot) && IsUnderPath(runRoot, imgsRoot))
            {
                foreach (var folderName in new[] { "previews", "finals" })
                {
                    var folder = Path.Combine(runRoot, folderName);
                    if (!Directory.Exists(folder))
                    {
                        continue;
                    }

                    var preview = FindMatchingPreview(folder, previewNames, recursive: false);
                    if (preview != null)
                    {
                        return preview;
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Log($"Preview lookup skipped: {ex.Message}");
        }

        return null;
    }

    private static List<string> BuildPreviewNameCandidates(string jsonStem)
    {
        var candidates = new List<string> { jsonStem };
        var dot = jsonStem.LastIndexOf('.');
        if (dot > 0 && dot < jsonStem.Length - 1)
        {
            var suffix = jsonStem[(dot + 1)..];
            if (suffix.EndsWith("v2", StringComparison.OrdinalIgnoreCase) &&
                suffix[..^2].All(char.IsDigit))
            {
                var prefix = jsonStem[..dot];
                candidates.Add($"{prefix}.preview.{suffix}");
                candidates.Add($"{prefix}.final.{suffix}");
            }
        }

        return candidates
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static string? FindMatchingPreview(string folder, List<string> previewNames, bool recursive)
    {
        var option = recursive ? SearchOption.AllDirectories : SearchOption.TopDirectoryOnly;
        var files = Directory.EnumerateFiles(folder, "*.png", option)
            .Select(path => new
            {
                Path = path,
                Stem = Path.GetFileNameWithoutExtension(path),
                Modified = File.GetLastWriteTimeUtc(path)
            })
            .ToList();

        var exact = files
            .Where(file => previewNames.Any(name => string.Equals(file.Stem, name, StringComparison.OrdinalIgnoreCase)))
            .OrderByDescending(file => file.Modified)
            .FirstOrDefault();
        if (exact != null)
        {
            return exact.Path;
        }

        return files
            .Where(file => previewNames.Any(name => file.Stem.Contains(name, StringComparison.OrdinalIgnoreCase)))
            .OrderByDescending(file => file.Modified)
            .FirstOrDefault()?.Path;
    }

    private static bool IsUnderPath(string candidatePath, string rootPath)
    {
        var candidate = Path.GetFullPath(candidatePath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var root = Path.GetFullPath(rootPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return candidate.StartsWith(root, StringComparison.OrdinalIgnoreCase);
    }

    private string? RenderJsonPreviewFallback(string jsonPath)
    {
        try
        {
            var bridge = Path.Combine(_appRoot, "KFPS.Wpf", "wpf_json_preview_bridge.py");
            if (!File.Exists(bridge))
            {
                return null;
            }

            var fullPath = Path.GetFullPath(jsonPath);
            var fingerprint = $"{fullPath}|{File.GetLastWriteTimeUtc(fullPath).Ticks}|{new FileInfo(fullPath).Length}";
            var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(fingerprint)))[..16].ToLowerInvariant();
            var cachePath = Path.Combine(_appRoot, "runtime", "wpf-json-previews", $"{hash}.png");
            if (File.Exists(cachePath))
            {
                return cachePath;
            }

            var python = ResolvePythonExecutable();
            if (python == null)
            {
                Log("JSON preview needs the bundled Python runtime. Check the bundle in Settings.");
                return null;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = $"-u {Quote(bridge)} --app-root {Quote(_appRoot)} --json {Quote(fullPath)} --output {Quote(cachePath)} --max-size 900",
                WorkingDirectory = _appRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };

            using var process = Process.Start(startInfo);
            if (process == null)
            {
                return null;
            }

            var stdout = process.StandardOutput.ReadToEnd();
            var stderr = process.StandardError.ReadToEnd();
            if (!process.WaitForExit(8000))
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                Log("JSON preview render timed out.");
                return null;
            }

            if (process.ExitCode == 0 && File.Exists(cachePath))
            {
                return cachePath;
            }

            var message = string.IsNullOrWhiteSpace(stderr) ? stdout.Trim() : stderr.Trim();
            if (!string.IsNullOrWhiteSpace(message))
            {
                Log($"JSON preview render unavailable: {message}");
            }
        }
        catch (Exception ex)
        {
            Log($"JSON preview render failed: {ex.Message}");
        }

        return null;
    }

    private string? FindNewestPreviewInRun(string? runFolder)
    {
        if (string.IsNullOrWhiteSpace(runFolder) || !Directory.Exists(runFolder))
        {
            return null;
        }

        var previewDir = Path.Combine(runFolder, "previews");
        if (Directory.Exists(previewDir))
        {
            var rawPreview = Directory.EnumerateFiles(previewDir, "*.raw.preview.png", SearchOption.TopDirectoryOnly)
                .OrderByDescending(File.GetLastWriteTimeUtc)
                .FirstOrDefault();
            if (rawPreview != null)
            {
                return rawPreview;
            }

            var topPreview = Directory.EnumerateFiles(previewDir, "*.png", SearchOption.TopDirectoryOnly)
                .Where(path => path.Contains("preview", StringComparison.OrdinalIgnoreCase) ||
                               path.Contains("heatmap", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(File.GetLastWriteTimeUtc)
                .FirstOrDefault();
            if (topPreview != null)
            {
                return topPreview;
            }
        }

        var finalsDir = Path.Combine(runFolder, "finals");
        if (Directory.Exists(finalsDir))
        {
            var finalPreview = Directory.EnumerateFiles(finalsDir, "*.png", SearchOption.TopDirectoryOnly)
                .OrderByDescending(File.GetLastWriteTimeUtc)
                .FirstOrDefault();
            if (finalPreview != null)
            {
                return finalPreview;
            }
        }

        var candidates = Directory.EnumerateFiles(runFolder, "*.png", SearchOption.TopDirectoryOnly)
            .Where(path => path.Contains($"{Path.DirectorySeparatorChar}previews{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase) ||
                           path.Contains($"{Path.DirectorySeparatorChar}finals{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase) ||
                           path.Contains("preview", StringComparison.OrdinalIgnoreCase) ||
                           path.Contains("heatmap", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .ToList();
        return candidates.FirstOrDefault();
    }

    private static void SetImage(Image image, FrameworkElement placeholder, string? fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName) || !File.Exists(fileName))
        {
            image.Source = null;
            placeholder.Visibility = Visibility.Visible;
            return;
        }

        try
        {
            var bitmap = new BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.CreateOptions = BitmapCreateOptions.IgnoreImageCache;
            bitmap.UriSource = new Uri(fileName, UriKind.Absolute);
            bitmap.DecodePixelWidth = 900;
            bitmap.EndInit();
            bitmap.Freeze();
            image.Source = bitmap;
            placeholder.Visibility = Visibility.Collapsed;
        }
        catch
        {
            image.Source = null;
            placeholder.Visibility = Visibility.Visible;
        }
    }

    private string CreateSourceHeatmapPreview(string sourceFile)
    {
        var outputFolder = Path.Combine(_appRoot, "runtime", "wpf-heatmaps");
        Directory.CreateDirectory(outputFolder);
        var outputFile = Path.Combine(outputFolder, Path.GetFileNameWithoutExtension(sourceFile) + ".heatmap.png");

        var source = new BitmapImage();
        source.BeginInit();
        source.CacheOption = BitmapCacheOption.OnLoad;
        source.CreateOptions = BitmapCreateOptions.IgnoreImageCache;
        source.UriSource = new Uri(sourceFile, UriKind.Absolute);
        source.DecodePixelWidth = 1400;
        source.EndInit();
        source.Freeze();

        var converted = new FormatConvertedBitmap(source, PixelFormats.Bgra32, null, 0);
        var width = converted.PixelWidth;
        var height = converted.PixelHeight;
        var stride = width * 4;
        var pixels = new byte[stride * height];
        converted.CopyPixels(pixels, stride, 0);

        var luma = new byte[width * height];
        for (var i = 0; i < width * height; i++)
        {
            var p = i * 4;
            var b = pixels[p];
            var g = pixels[p + 1];
            var r = pixels[p + 2];
            var a = pixels[p + 3];
            luma[i] = a < 12 ? (byte)0 : (byte)Math.Clamp((r * 54 + g * 183 + b * 19) >> 8, 0, 255);
        }

        var output = new byte[pixels.Length];
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var i = y * width + x;
                var p = i * 4;
                var alpha = pixels[p + 3];
                if (alpha < 12)
                {
                    output[p + 3] = 0;
                    continue;
                }

                var left = luma[y * width + Math.Max(0, x - 1)];
                var right = luma[y * width + Math.Min(width - 1, x + 1)];
                var up = luma[Math.Max(0, y - 1) * width + x];
                var down = luma[Math.Min(height - 1, y + 1) * width + x];
                var edge = Math.Min(255, Math.Abs(right - left) + Math.Abs(down - up));
                var detail = Math.Clamp(edge * 2, 0, 255);

                // Blue marks low-detail source regions; pink/yellow marks areas likely to need more shapes.
                output[p] = (byte)Math.Clamp(120 - detail / 4, 0, 255);
                output[p + 1] = (byte)Math.Clamp(40 + detail / 2, 0, 255);
                output[p + 2] = (byte)Math.Clamp(70 + detail, 0, 255);
                output[p + 3] = alpha;
            }
        }

        var bitmap = BitmapSource.Create(width, height, source.DpiX, source.DpiY, PixelFormats.Bgra32, null, output, stride);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var stream = File.Create(outputFile);
        encoder.Save(stream);
        return outputFile;
    }

    private void SetupPython(object sender, RoutedEventArgs e)
    {
        var bundled = Path.Combine(_appRoot, "python", "python.exe");
        if (IsUsablePythonExecutable(bundled))
        {
            Log("Bundled Python is ready. No download or external Python install is needed.");
            MessageBox.Show(this, "Bundled Python is already included and ready. No download is needed.", "Python ready", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        Log("Bundled Python is missing or incomplete. This native package should be replaced with a complete bundle.");
        MessageBox.Show(this, "Bundled Python is missing or incomplete. Re-extract or replace the KFPS package; the native bundle should not need a Python download.", "Bundled Python missing", MessageBoxButton.OK, MessageBoxImage.Warning);
    }

    private void InstallDependencies(object sender, RoutedEventArgs e)
    {
        var bundled = Path.Combine(_appRoot, "python", "python.exe");
        if (IsUsablePythonExecutable(bundled))
        {
            var report = EvaluatePythonEnvironment();
            if (report.Ready)
            {
                Log("Bundled Python dependencies are ready. No download is needed.");
                MessageBox.Show(this, "Bundled dependencies are already included and ready. No download is needed.", "Dependencies ready", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            Log($"Bundled dependency check failed: {report.Message}", updateStatus: false);
            MessageBox.Show(this, "Bundled Python exists, but one or more included dependencies are missing or broken. Re-extract or replace the KFPS package; the native bundle should not need pip downloads.", "Bundled dependencies incomplete", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        Log("Bundled Python is missing. Dependency checks cannot run in the native package.");
        MessageBox.Show(this, "Bundled Python is missing, so dependencies cannot be verified. Re-extract or replace the KFPS package.", "Bundled Python missing", MessageBoxButton.OK, MessageBoxImage.Warning);
    }
    private void UpdateFromGitHub(object sender, RoutedEventArgs e)
    {
        var batchPath = Path.Combine(_appRoot, "03_update_from_github.bat");
        if (!File.Exists(batchPath))
        {
            Log($"Missing updater: {batchPath}");
            MessageBox.Show(this, "The updater batch file is missing from this package.", "Updater missing", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        var response = MessageBox.Show(
            this,
            "KFPS needs to close before updating so Windows can replace the native app safely.\n\nThe updater will keep generated images and runtime data, then relaunch KFPS if the update succeeds.",
            "Update KFPS",
            MessageBoxButton.OKCancel,
            MessageBoxImage.Information);
        if (response != MessageBoxResult.OK)
        {
            return;
        }

        StartNativeUpdateHandoff(batchPath);
    }

    private void StartNativeUpdateHandoff(string batchPath)
    {
        try
        {
            var parentRoot = Directory.GetParent(_appRoot)?.FullName ?? _appRoot;
            var handoffDir = Path.Combine(_appRoot, "runtime", "native-update");
            Directory.CreateDirectory(handoffDir);

            var scriptPath = Path.Combine(handoffDir, "run-native-update.ps1");
            var logPath = Path.Combine(handoffDir, "native-update-handoff.log");
            File.WriteAllText(scriptPath, BuildNativeUpdateHandoffScript(
                _appRoot,
                parentRoot,
                batchPath,
                Environment.ProcessId,
                logPath), Encoding.UTF8);

            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = $"-NoProfile -ExecutionPolicy Bypass -File {Quote(scriptPath)}",
                WorkingDirectory = _appRoot,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(startInfo);
            Log("Updater handoff started. Closing KFPS so files can be replaced safely.");
            Application.Current.Shutdown();
        }
        catch (Exception ex)
        {
            Log($"Failed to start native updater handoff: {ex.Message}");
            MessageBox.Show(this, $"Could not start the updater handoff.\n\n{ex.Message}", "Update failed to start", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }

    private static string BuildNativeUpdateHandoffScript(string appRoot, string parentRoot, string batchPath, int parentPid, string logPath)
    {
        static string PsLiteral(string value) => "'" + value.Replace("'", "''") + "'";

        return $$"""
$ErrorActionPreference = 'Continue'
$appRoot = {{PsLiteral(appRoot)}}
$parentRoot = {{PsLiteral(parentRoot)}}
$batchPath = {{PsLiteral(batchPath)}}
$logPath = {{PsLiteral(logPath)}}
$parentPid = {{parentPid}}

function Write-HandoffLog([string]$message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $dir = Split-Path -Parent $logPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    "[$stamp] $message" | Add-Content -LiteralPath $logPath -Encoding UTF8
}

Write-HandoffLog "Native update handoff started."
try {
    $parent = Get-Process -Id $parentPid -ErrorAction SilentlyContinue
    if ($parent) {
        Write-HandoffLog "Waiting for KFPS process $parentPid to exit."
        Wait-Process -Id $parentPid -Timeout 60 -ErrorAction SilentlyContinue
    }
} catch {
    Write-HandoffLog ("Parent wait warning: " + $_.Exception.Message)
}

Start-Sleep -Milliseconds 500
$env:FORZA_PAINTER_NO_PAUSE = '1'
Write-HandoffLog "Running updater batch."
$process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/c', "`"$batchPath`"") -WorkingDirectory $appRoot -Wait -PassThru -WindowStyle Normal
$exitCode = if ($process) { $process.ExitCode } else { 1 }
Write-HandoffLog "Updater batch exited with code $exitCode."

if ($exitCode -eq 0) {
    $kfps = Join-Path $parentRoot 'KFPS.exe'
    if (Test-Path -LiteralPath $kfps) {
        Write-HandoffLog "Relaunching KFPS."
        Start-Process -FilePath $kfps -WorkingDirectory $parentRoot
    } else {
        Write-HandoffLog "KFPS.exe was not found after update."
    }
}

Write-HandoffLog "Native update handoff finished."
""";
    }

    private void FirstLaunchInstallPython(object sender, RoutedEventArgs e)
    {
        var bundled = Path.Combine(_appRoot, "python", "python.exe");
        if (IsUsablePythonExecutable(bundled))
        {
            FirstLaunchStatusText.Text = "Bundled Python is already included. Click Launch to verify dependencies.";
            Log("First launch check: bundled Python is ready; no external install needed.");
            CheckFirstLaunchSetup(forceVisibleOnFailure: true);
            return;
        }

        FirstLaunchStatusText.Text = "Bundled Python is missing or incomplete. Re-extract or replace the KFPS package.";
        Log("First launch check: bundled Python missing or incomplete.");
    }

    private void FirstLaunchInstallDependencies(object sender, RoutedEventArgs e)
    {
        var report = EvaluatePythonEnvironment();
        if (!report.PythonPresent)
        {
            FirstLaunchStatusText.Text = "Bundled Python is missing. Re-extract or replace the KFPS package.";
            Log("First launch check: bundled Python missing; dependency check cannot continue.");
            return;
        }

        if (IsUsablePythonExecutable(Path.Combine(_appRoot, "python", "python.exe")))
        {
            FirstLaunchStatusText.Text = "Bundled dependencies should already be included. Checking them now.";
            CheckFirstLaunchSetup(forceVisibleOnFailure: true);
            return;
        }

        FirstLaunchStatusText.Text = "Bundled Python is missing, so dependencies cannot be verified. Re-extract or replace the KFPS package.";
        Log("First launch check: dependency check refused because bundled Python is missing.");
    }

    private void FirstLaunchVerifyAndLaunch(object sender, RoutedEventArgs e)
    {
        CheckFirstLaunchSetup(forceVisibleOnFailure: true);
    }

    private void CheckFirstLaunchSetup(bool forceVisibleOnFailure = false)
    {
        var report = EvaluatePythonEnvironment();
        if (report.Ready)
        {
            FirstLaunchOverlay.Visibility = Visibility.Collapsed;
            Log("Python and dependencies verified.", updateStatus: false);
            return;
        }

        FirstLaunchOverlay.Visibility = Visibility.Visible;
        FirstLaunchStatusText.Text = report.Message;
        FirstLaunchPythonButton.IsEnabled = !report.PythonPresent;
        FirstLaunchDepsButton.IsEnabled = report.PythonPresent;
        FirstLaunchLaunchButton.Content = forceVisibleOnFailure ? "Check again" : "Launch";
        Log($"First launch check requires attention: {report.Message}", updateStatus: false);
    }

    private SetupReport EvaluatePythonEnvironment()
    {
        var python = ResolvePythonExecutable();
        if (python == null)
        {
            return new SetupReport(false, false, "Bundled Python was not found. Re-extract or replace the KFPS package.");
        }

        var imports = new[]
        {
            ("Pillow", "PIL"),
            ("NumPy", "numpy"),
            ("OpenCV", "cv2"),
            ("psutil", "psutil"),
            ("pywin32", "win32api")
        };
        var importScript = "import importlib, sys\n" +
                           "mods = " + JsonSerializer.Serialize(imports.Select(item => item.Item2).ToArray()) + "\n" +
                           "missing = []\n" +
                           "for mod in mods:\n" +
                           "    try:\n" +
                           "        importlib.import_module(mod)\n" +
                           "    except Exception:\n" +
                           "        missing.append(mod)\n" +
                           "print(','.join(missing))\n" +
                           "sys.exit(1 if missing else 0)\n";

        try
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = python,
                    Arguments = "-c " + Quote(importScript),
                    WorkingDirectory = _appRoot,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                }
            };
            process.Start();
            if (!process.WaitForExit(8000))
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                return new SetupReport(true, false, "Bundled Python exists, but dependency verification timed out. Click Check again; re-extract the package if this repeats.");
            }

            var stdout = process.StandardOutput.ReadToEnd().Trim();
            var stderr = process.StandardError.ReadToEnd().Trim();
            if (process.ExitCode == 0)
            {
                return new SetupReport(true, true, "Python and dependencies are ready.");
            }

            var missingModules = stdout.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            var missingNames = imports
                .Where(item => missingModules.Contains(item.Item2, StringComparer.OrdinalIgnoreCase))
                .Select(item => item.Item1)
                .ToList();
            var missingText = missingNames.Count > 0 ? string.Join(", ", missingNames) : "one or more required packages";
            var detail = string.IsNullOrWhiteSpace(stderr) ? "" : $"\n\nDetails: {stderr}";
            return new SetupReport(true, false, $"Bundled Python is present, but dependencies are missing: {missingText}. Re-extract or replace the KFPS package.{detail}");
        }
        catch (Exception ex)
        {
            return new SetupReport(true, false, $"Bundled Python exists, but verification failed: {ex.Message}. Re-extract the package if this repeats.");
        }
    }

    private string? ResolvePythonExecutable()
    {
        var bundled = Path.Combine(_appRoot, "python", "python.exe");
        if (IsUsablePythonExecutable(bundled))
        {
            return bundled;
        }

        var local = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs",
            "Python",
            "Python312",
            "python.exe");
        if (IsUsablePythonExecutable(local))
        {
            return local;
        }

        return ResolvePythonFromCommand("py", "-3.12") ??
               ResolvePythonFromCommand("python", "");
    }

    private static bool IsUsablePythonExecutable(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return false;
        }

        try
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = path,
                    Arguments = "-c \"import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                }
            };
            process.Start();
            return process.WaitForExit(3000) && process.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    private static string? ResolvePythonFromCommand(string command, string prefixArgs)
    {
        try
        {
            var probe = "import sys; raise SystemExit(1) if sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32 else print(sys.executable)";
            var args = string.IsNullOrWhiteSpace(prefixArgs)
                ? $"-c {Quote(probe)}"
                : $"{prefixArgs} -c {Quote(probe)}";
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = command,
                    Arguments = args,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                }
            };
            process.Start();
            if (!process.WaitForExit(3000) || process.ExitCode != 0)
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                return null;
            }

            var executable = process.StandardOutput.ReadToEnd().Trim();
            return IsUsablePythonExecutable(executable) ? executable : null;
        }
        catch
        {
            return null;
        }
    }

    private void StartFabricEditor(object sender, RoutedEventArgs e)
    {
        StartFabricEditorWithProject(null);
    }

    private void StartFabricEditorWithProject(string? projectPath)
    {
        var launcher = Path.Combine(_appRoot, "tools", "fabric-editor", "start_fabric_editor.py");
        if (!File.Exists(launcher))
        {
            Log($"Fabric editor launcher not found: {launcher}");
            return;
        }

        var python = ResolvePythonExecutable();
        if (python == null)
        {
            Log("Fabric editor needs the bundled Python runtime. Check the bundle in Settings.");
            CheckFirstLaunchSetup(forceVisibleOnFailure: true);
            return;
        }

        var args = new StringBuilder(Quote(launcher));
        if (!string.IsNullOrWhiteSpace(projectPath))
        {
            var relativeProject = Path.GetRelativePath(EditorProjectRoot(), projectPath);
            args.Append(" --project-id ").Append(Quote(relativeProject.Replace('\\', '/')));
            Log($"Opening editor project: {projectPath}");
        }

        RunHiddenDetached(python, args.ToString(), _appRoot);
    }

    private void OpenGeneratedFolder(object sender, RoutedEventArgs e) => OpenFolder(Path.Combine(_appRoot, "imgs", "generated"));
    private void OpenJsonFolders(object sender, RoutedEventArgs e) => OpenFolder(Path.Combine(_appRoot, "imgs"));
    private void OpenSelectedJsonSourceFolder(object sender, RoutedEventArgs e) => OpenFolder(GetSelectedJsonSource().Root);
    private void OpenRuntimeFolder(object sender, RoutedEventArgs e) => OpenFolder(Path.Combine(_appRoot, "runtime"));
    private void OpenEditorFolder(object sender, RoutedEventArgs e) => OpenFolder(Path.Combine(_appRoot, "tools", "fabric-editor"));
    private void OpenEditorExportsFolder(object sender, RoutedEventArgs e) => OpenFolder(Path.Combine(_appRoot, "imgs", "editor"));
    private void OpenEditorProjectsFolder(object sender, RoutedEventArgs e) => OpenFolder(EditorProjectRoot());
    private void OpenReportsFolder(object sender, RoutedEventArgs e) => OpenFolder(Path.Combine(_appRoot, "runtime", "bug-reports"));
    private void OpenAppRoot(object sender, RoutedEventArgs e) => OpenFolder(_appRoot);

    private string GetStandaloneImagesFolder()
    {
        var standaloneRoot = Directory.GetParent(_appRoot)?.FullName;
        var imagesFolder = standaloneRoot == null ? "" : Path.Combine(standaloneRoot, "Images");
        return Directory.Exists(imagesFolder) ? imagesFolder : _appRoot;
    }

    private static string GetComboText(ComboBox comboBox, string fallback)
    {
        if (comboBox.SelectedItem is ComboBoxItem item)
        {
            return item.Content?.ToString() ?? fallback;
        }

        return comboBox.Text?.Trim() is { Length: > 0 } text ? text : fallback;
    }

    private void LayerComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        UpdateFinalCheckpointsForSelectedLayers();
    }

    private void LayerComboBox_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        e.Handled = true;
        var current = ParseLayerCount(GetComboText(LayerComboBox, "2000")) ?? 2000;
        if (!TryPromptLayerCount(current, out var layers))
        {
            return;
        }

        SelectOrAddLayerCount(layers);
        UpdateFinalCheckpointsForSelectedLayers();
        Log($"Custom layer count selected: {layers}. Final checkpoints adjusted automatically.");
    }

    private static int? ParseLayerCount(string? text)
    {
        if (int.TryParse((text ?? "").Trim(), out var value) && value is >= 1 and <= 3000)
        {
            return value;
        }

        return null;
    }

    private void SelectOrAddLayerCount(int layers)
    {
        var label = layers.ToString();
        for (var i = 0; i < LayerComboBox.Items.Count; i++)
        {
            if (LayerComboBox.Items[i] is ComboBoxItem item &&
                string.Equals(item.Content?.ToString(), label, StringComparison.OrdinalIgnoreCase))
            {
                LayerComboBox.SelectedIndex = i;
                return;
            }
        }

        var newItem = new ComboBoxItem { Content = label };
        var insertAt = LayerComboBox.Items.Count;
        for (var i = 0; i < LayerComboBox.Items.Count; i++)
        {
            if (LayerComboBox.Items[i] is ComboBoxItem item &&
                int.TryParse(item.Content?.ToString(), out var existing) &&
                layers < existing)
            {
                insertAt = i;
                break;
            }
        }

        LayerComboBox.Items.Insert(insertAt, newItem);
        LayerComboBox.SelectedItem = newItem;
    }

    private void UpdateFinalCheckpointsForSelectedLayers()
    {
        if (FinalCheckpointsTextBox == null || LayerComboBox == null)
        {
            return;
        }

        var layers = ParseLayerCount(GetComboText(LayerComboBox, "2000")) ?? 2000;
        FinalCheckpointsTextBox.Text = BuildFinalCheckpointLine(layers);
    }

    private static string BuildFinalCheckpointLine(int layers)
    {
        layers = Math.Clamp(layers, 1, 3000);
        var checkpoints = new SortedSet<int>();

        if (layers < 500)
        {
            foreach (var fraction in new[] { 0.25, 0.5, 0.75, 1.0 })
            {
                var value = RoundCheckpoint((int)Math.Round(layers * fraction), layers);
                if (value > 0)
                {
                    checkpoints.Add(value);
                }
            }
        }
        else
        {
            foreach (var milestone in new[] { 500, 1000, 1250, 1500, 2000, 2500, 3000 })
            {
                if (milestone <= layers)
                {
                    checkpoints.Add(milestone);
                }
            }

            checkpoints.Add(layers);
        }

        return string.Join(",", checkpoints);
    }

    private static int RoundCheckpoint(int value, int max)
    {
        if (max <= 100)
        {
            return Math.Clamp(value, 1, max);
        }

        var step = max <= 500 ? 25 : 50;
        var rounded = Math.Max(step, (int)Math.Round(value / (double)step) * step);
        return Math.Clamp(rounded, 1, max);
    }

    private bool TryPromptLayerCount(int current, out int layers)
    {
        layers = current;
        var selectedLayers = current;

        var dialog = new Window
        {
            Title = "Custom layer count",
            Owner = this,
            Width = 360,
            Height = 184,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            ResizeMode = ResizeMode.NoResize,
            Background = (Brush)FindResource("PanelBrush"),
            Content = null
        };

        var root = new Grid { Margin = new Thickness(18) };
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var prompt = new TextBlock
        {
            Text = "Enter a custom layer count between 1 and 3000.",
            Foreground = (Brush)FindResource("InkBrush"),
            TextWrapping = TextWrapping.Wrap
        };
        Grid.SetRow(prompt, 0);
        root.Children.Add(prompt);

        var input = new TextBox
        {
            Text = current.ToString(),
            Margin = new Thickness(0, 12, 0, 12),
            MinHeight = 30
        };
        Grid.SetRow(input, 1);
        root.Children.Add(input);

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right
        };
        var ok = new Button { Content = "Use layers", MinWidth = 96, Margin = new Thickness(0, 0, 8, 0), IsDefault = true };
        var cancel = new Button { Content = "Cancel", MinWidth = 76, IsCancel = true };
        buttons.Children.Add(ok);
        buttons.Children.Add(cancel);
        Grid.SetRow(buttons, 2);
        root.Children.Add(buttons);

        ok.Click += (_, _) =>
        {
            if (ParseLayerCount(input.Text) is { } parsed)
            {
                selectedLayers = parsed;
                dialog.DialogResult = true;
                dialog.Close();
                return;
            }

            MessageBox.Show(dialog, "Layer count must be a whole number from 1 to 3000.", "Invalid layer count", MessageBoxButton.OK, MessageBoxImage.Warning);
            input.SelectAll();
            input.Focus();
        };

        dialog.Content = root;
        input.Loaded += (_, _) =>
        {
            input.Focus();
            input.SelectAll();
        };

        if (dialog.ShowDialog() == true)
        {
            layers = selectedLayers;
            return true;
        }

        return false;
    }

    private void SeedTextBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (_updatingSeedText)
        {
            return;
        }

        if (int.TryParse(SeedTextBox.Text.Trim(), out var seed) && seed > 0)
        {
            _seedLocked = true;
            _seedOneShot = false;
            UpdateSeedButtons();
            Log($"Seed locked: {seed}");
        }
    }

    private void ToggleSeedLock(object sender, RoutedEventArgs e)
    {
        if (_seedLocked)
        {
            _seedLocked = false;
            _seedOneShot = false;
            SetSeedText("-1");
            UpdateSeedButtons();
            Log("Seed unlocked. Future generations will use a new random seed.");
            return;
        }

        if (!int.TryParse(SeedTextBox.Text.Trim(), out var seed) || seed <= 0)
        {
            seed = NewGeneratorSeed();
            SetSeedText(seed.ToString());
        }

        _seedLocked = true;
        _seedOneShot = false;
        UpdateSeedButtons();
        Log($"Seed locked: {seed}");
    }

    private void RandomizeSeedOnce(object sender, RoutedEventArgs e)
    {
        var seed = NewGeneratorSeed();
        SetSeedText(seed.ToString());
        _seedLocked = false;
        _seedOneShot = true;
        UpdateSeedButtons();
        Log($"One-time seed rolled: {seed}. After the next generation, random seed mode resumes.");
    }

    private int EffectiveGenerationSeed()
    {
        if (ManualOverridesCheckBox?.IsChecked != true)
        {
            return -1;
        }

        if ((_seedLocked || _seedOneShot) && int.TryParse(SeedTextBox.Text.Trim(), out var seed) && seed > 0)
        {
            return seed;
        }

        return 0;
    }

    private void ResetOneShotSeedAfterStart()
    {
        if (!_seedOneShot)
        {
            return;
        }

        _seedOneShot = false;
        SetSeedText("-1");
        UpdateSeedButtons();
        Log("One-time seed consumed. Random seed mode restored.");
    }

    private static int NewGeneratorSeed()
    {
        return Random.Shared.Next(1, int.MaxValue);
    }

    private void SetSeedText(string text)
    {
        _updatingSeedText = true;
        try
        {
            SeedTextBox.Text = text;
        }
        finally
        {
            _updatingSeedText = false;
        }
    }

    private void UpdateSeedButtons()
    {
        if (_seedLocked)
        {
            SeedLockButton.SetResourceReference(Control.BackgroundProperty, "AccentDeepBrush");
            SeedLockButton.SetResourceReference(Control.BorderBrushProperty, "AccentBrush");
            SeedLockButton.ToolTip = "Seed is locked. Click to unlock random seed mode.";
        }
        else
        {
            SeedLockButton.SetResourceReference(Control.BackgroundProperty, "PanelLiftBrush");
            SeedLockButton.SetResourceReference(Control.BorderBrushProperty, "BorderBrushSoft");
            SeedLockButton.ToolTip = "Reuse current seed";
        }

        SeedDiceButton.ToolTip = _seedOneShot
            ? "One-time seed ready. It will be used for the next generation only."
            : "Roll one seed, then return to random each generation";
    }

    private void AutoSelectPresetForImage(string imagePath)
    {
        try
        {
            var key = AutoPresetKeyForImage(imagePath);
            var selectedIndex = key switch
            {
                "flat" => FindPresetIndex("flat"),
                "gradient" => FindPresetIndex("gradient"),
                _ => FindPresetIndex("shaded")
            };
            if (selectedIndex >= 0 && PresetComboBox.SelectedIndex != selectedIndex)
            {
                PresetComboBox.SelectedIndex = selectedIndex;
            }

            Log($"Auto preset: {PresetNameForKey(key)}.");
        }
        catch (Exception ex)
        {
            PresetComboBox.SelectedIndex = Math.Max(0, FindPresetIndex("shaded"));
            Log($"Auto preset detection unavailable, using Shaded Character Art: {ex.Message}");
        }
    }

    private int FindPresetIndex(string key)
    {
        for (var index = 0; index < PresetComboBox.Items.Count; index++)
        {
            var text = PresetComboBox.Items[index] is ComboBoxItem item
                ? item.Content?.ToString() ?? ""
                : PresetComboBox.Items[index]?.ToString() ?? "";
            var lower = text.ToLowerInvariant();
            if (key == "flat" && lower.Contains("flat"))
            {
                return index;
            }
            if (key == "gradient" && lower.Contains("gradient"))
            {
                return index;
            }
            if (key == "shaded" && (lower.Contains("shaded") || lower.Contains("character")))
            {
                return index;
            }
        }

        return key == "shaded" && PresetComboBox.Items.Count > 0 ? 0 : -1;
    }

    private static string PresetNameForKey(string key)
    {
        return key switch
        {
            "flat" => "Flat Colors",
            "gradient" => "Smooth Gradients",
            _ => "Shaded Character Art"
        };
    }

    private static string AutoPresetKeyForImage(string imagePath)
    {
        if (string.IsNullOrWhiteSpace(imagePath) || !File.Exists(imagePath))
        {
            return "shaded";
        }

        var source = new BitmapImage();
        source.BeginInit();
        source.CacheOption = BitmapCacheOption.OnLoad;
        source.CreateOptions = BitmapCreateOptions.IgnoreImageCache;
        source.UriSource = new Uri(imagePath, UriKind.Absolute);
        source.DecodePixelWidth = 384;
        source.DecodePixelHeight = 384;
        source.EndInit();
        source.Freeze();

        var bitmap = new FormatConvertedBitmap(source, PixelFormats.Bgra32, null, 0);
        var width = bitmap.PixelWidth;
        var height = bitmap.PixelHeight;
        var stride = width * 4;
        var pixels = new byte[stride * height];
        bitmap.CopyPixels(pixels, stride, 0);

        var visibleIndices = new List<int>(width * height);
        var gray = new byte[width * height];
        for (var i = 0; i < width * height; i++)
        {
            var p = i * 4;
            var b = pixels[p];
            var g = pixels[p + 1];
            var r = pixels[p + 2];
            var a = pixels[p + 3];
            gray[i] = (byte)Math.Clamp((r * 54 + g * 183 + b * 19) >> 8, 0, 255);
            if (a > 24)
            {
                visibleIndices.Add(i);
            }
        }

        if (visibleIndices.Count < 32)
        {
            return "shaded";
        }

        var edgeHits = 0;
        var colorBins = new HashSet<int>();
        var sampleStep = Math.Max(1, visibleIndices.Count / 20000);
        double lumaSum = 0;
        double lumaSquaredSum = 0;
        double localDetailSum = 0;
        var sampled = 0;

        for (var visibleIndex = 0; visibleIndex < visibleIndices.Count; visibleIndex++)
        {
            var i = visibleIndices[visibleIndex];
            var x = i % width;
            var y = i / width;
            var center = gray[i];
            lumaSum += center;
            lumaSquaredSum += center * center;

            var left = gray[y * width + Math.Max(0, x - 1)];
            var right = gray[y * width + Math.Min(width - 1, x + 1)];
            var up = gray[Math.Max(0, y - 1) * width + x];
            var down = gray[Math.Min(height - 1, y + 1) * width + x];
            var edge = Math.Abs(right - left) + Math.Abs(down - up);
            if (edge > 80)
            {
                edgeHits++;
            }

            var blur =
                (left + right + up + down + center +
                 gray[Math.Max(0, y - 1) * width + Math.Max(0, x - 1)] +
                 gray[Math.Max(0, y - 1) * width + Math.Min(width - 1, x + 1)] +
                 gray[Math.Min(height - 1, y + 1) * width + Math.Max(0, x - 1)] +
                 gray[Math.Min(height - 1, y + 1) * width + Math.Min(width - 1, x + 1)]) / 9.0;
            localDetailSum += Math.Abs(center - blur);

            if (visibleIndex % sampleStep == 0)
            {
                var p = i * 4;
                var rBin = pixels[p + 2] / 24;
                var gBin = pixels[p + 1] / 24;
                var bBin = pixels[p] / 24;
                colorBins.Add((rBin << 16) | (gBin << 8) | bBin);
                sampled++;
            }
        }

        var count = Math.Max(1, visibleIndices.Count);
        var edgeDensity = edgeHits / (double)count;
        var colorBinCount = colorBins.Count;
        var colorRatio = colorBinCount / (double)Math.Max(1, sampled);
        var lumaMean = lumaSum / count;
        var lumaVariance = Math.Max(0, lumaSquaredSum / count - lumaMean * lumaMean);
        var lumaStd = Math.Sqrt(lumaVariance);
        var localDetail = localDetailSum / count;

        if (colorBinCount <= 90 && colorRatio < 0.030 && edgeDensity >= 0.045)
        {
            return "flat";
        }

        if (edgeDensity < 0.070 && colorBinCount >= 140 && localDetail < 12.0 && lumaStd >= 28.0)
        {
            return "gradient";
        }

        return "shaded";
    }

    private void OpenKofi(object sender, RoutedEventArgs e)
    {
        OpenExternalUrl("https://ko-fi.com/kloudy1811", "Ko-fi support page");
    }

    private void OpenBackgroundRemover(object sender, RoutedEventArgs e)
    {
        OpenExternalUrl("https://www.photoroom.com/tools/background-remover", "background remover");
    }

    private void OpenBrowserUpscaler(object sender, RoutedEventArgs e)
    {
        OpenExternalUrl("https://hcodx.com/tools/image-upscaler", "browser upscaler");
    }

    private void OpenSquoosh(object sender, RoutedEventArgs e)
    {
        OpenExternalUrl("https://squoosh.app", "resize/compress tool");
    }

    private void OpenExternalUrl(string url, string label)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            });
            Log($"Opened {label}.");
        }
        catch (Exception ex)
        {
            Log($"Failed to open {label}: {ex.Message}");
        }
    }

    private void ShowTutorialTopic(object sender, RoutedEventArgs e)
    {
        var key = (sender as FrameworkElement)?.Tag?.ToString() ?? "workflow";
        if (!string.Equals(PageTitle.Text, "Help", StringComparison.OrdinalIgnoreCase))
        {
            ShowView("Help", TutorialView);
        }

        DisplayTutorialTopic(key);
        Log($"Tutorial topic opened: {key}");
    }

    private void InitializeTutorial()
    {
        if (_tutorialInitialized)
        {
            return;
        }

        var search = FindControl<TextBox>("TutorialSearchTextBox");
        if (search != null && string.IsNullOrWhiteSpace(search.Text))
        {
            search.Text = "";
        }

        DisplayTutorialTopic("workflow");
        _tutorialInitialized = true;
    }

    private void DisplayTutorialTopic(string key)
    {
        var title = FindControl<TextBlock>("TutorialContentTitle");
        var summary = FindControl<TextBlock>("TutorialContentSummary");
        var content = FindControl<TextBlock>("TutorialContentText");
        if (title == null || summary == null || content == null)
        {
            Log("Tutorial content panel was not found.");
            return;
        }

        var topic = BuildTutorialTopic(key);
        title.Text = topic.Title;
        summary.Text = topic.Summary;
        content.Text = topic.Body;
    }

    private TutorialTopic BuildTutorialTopic(string key)
    {
        return key switch
        {
            "generate" =>
                new TutorialTopic(
                    "Generate vinyls",
                    "How to turn source art into finalized JSON checkpoints.",
                    "1. Open Generate.\n" +
                    "2. Choose a source image from the Images folder or any local path.\n" +
                    "3. Let auto preset detection pick the closest preset, or choose one manually.\n" +
                    "4. Pick the target layer count. Finalize checkpoints are derived from that target.\n" +
                    "5. Leave Edge Repair off unless you specifically need it for that source.\n" +
                    "6. Use 2x mode when you want a heavier run and can spare the extra time.\n" +
                    "7. Press Generate Final Vinyl and watch the log for backend progress.\n\n" +
                    "Output:\n" +
                    "Generated JSONs and previews are written under imgs/generated. The JSON browser can select finalized checkpoints for import.\n\n" +
                    "Practical note:\n" +
                    "Generation is not AI. It searches for game vinyl shapes that approximate the source. The editor is still the best place for tiny text, eyes, logos, and deliberate sharp cleanup."),
            "images" =>
                new TutorialTopic(
                    "Image preparation",
                    "Use the Images tab before long runs.",
                    "The Images tab previews the source and reports resolution, megapixels, transparency, and a color-coded source check.\n\n" +
                    "Green means the source size is practical.\n" +
                    "Yellow means the source is usable but may waste time or lose detail.\n" +
                    "Red means it is clearly too small or too large and should be resized first.\n\n" +
                    "Transparent PNGs are preferred. If the background only looks removed but is actually opaque, the generator will spend shapes on background content.\n\n" +
                    "Large images are not always better. Overly huge sources can slow down generation and create noisy detail that does not survive the game shape limit.\n\n" +
                    "Use Tools for background removal, browser upscaling, and resizing/compression helpers."),
            "json" =>
                new TutorialTopic(
                    "JSON browser",
                    "Choose the exact JSON before importing.",
                    "Open JSON and pick a source folder:\n" +
                    "Generated finals: checkpoints created by the generator.\n" +
                    "Editor exports: JSONs saved from the vinyl editor.\n" +
                    "Exported game JSONs: vinyls exported from FH6/FM8 plus downloaded or manually placed JSONs.\n\n" +
                    "The browser shows generations/folders, JSON files, and a preview/details panel. Select the specific checkpoint you want before importing.\n\n" +
                    "If the selected path line does not change after choosing a JSON, stop and refresh the browser before importing."),
            "editor" =>
                new TutorialTopic(
                    "Editor basics",
                    "Hand-edit generated vinyls or make vinyls from scratch.",
                    "Open Editor starts the bundled Fabric vinyl editor.\n\n" +
                    "Common uses:\n" +
                    "Clean generated shapes.\n" +
                    "Build vinyls manually from source overlays.\n" +
                    "Use snap/grid/guides for alignment.\n" +
                    "Group layers internally without changing game export structure.\n" +
                    "Adjust masks, colors, opacity, transforms, and layer order.\n" +
                    "Export an import-ready JSON back into the app.\n\n" +
                    "Projects are internal working files under runtime/fabric-editor/projects. Exported JSONs are separate and are meant for the JSON browser/import flow."),
            "import" =>
                new TutorialTopic(
                    "Import / Export",
                    "Move JSONs between KFPS and supported game editors.",
                    "Import:\n" +
                    "1. Open a fresh template inside the game vinyl editor.\n" +
                    "2. Save and reload the template if shape resources look stale.\n" +
                    "3. Enter the loaded template layer count.\n" +
                    "4. Select the JSON in the browser or browse manually.\n" +
                    "5. Press Import JSON.\n\n" +
                    "Export:\n" +
                    "1. Open an editable, user-owned vinyl in the game editor.\n" +
                    "2. Ungroup it first when possible. Grouped/nested vinyls are harder to locate safely.\n" +
                    "3. Enter the visible layer count exactly.\n" +
                    "4. Choose the target game and press Export JSON.\n\n" +
                    "FM8 export is experimental and converted toward the FH-compatible JSON shape structure where supported."),
            "reports" =>
                new TutorialTopic(
                    "Bug reports",
                    "Create local reports without uploading private data.",
                    "Reports are generated locally only. KFPS does not automatically upload screenshots, JSONs, source images, memory dumps, or personal paths.\n\n" +
                    "Use Reports when something breaks and paste the saved report into Discord/GitHub manually.\n\n" +
                    "For import/export bugs, include the exact log lines and whether the game editor was showing FH6, FH5, or FM8."),
            "setup" =>
                new TutorialTopic(
                    "Checks and updates",
                    "Verify the bundled runtime and update app files.",
                    "KFPS 3.x ships with the Python runtime and backend packages it needs. The Settings page checks that those bundled files are present and usable.\n\n" +
                    "Check bundled Python confirms the packaged Python runtime.\n" +
                    "Check dependencies confirms the included backend modules.\n" +
                    "Update from GitHub updates app files while preserving runtime/generated data.\n\n" +
                    "If a check says files are missing, re-extract the package before assuming your Windows install is broken."),
            "troubleshooting" =>
                new TutorialTopic(
                    "Troubleshooting",
                    "Where to look first when something fails.",
                    "Generation fails:\n" +
                    "Read the log line immediately before the exit code. OpenCL errors usually mean driver/runtime/GPU resource trouble, not a JSON problem.\n\n" +
                    "Import/export cannot find the group:\n" +
                    "Confirm the game is open, the vinyl editor is loaded, the layer count is exact, and the app is running with enough permissions.\n\n" +
                    "Wrong JSON imports:\n" +
                    "Check the selected JSON path line and refresh the browser. Do not assume the latest file is selected.\n\n" +
                    "Editor feels slow:\n" +
                    "Large generated JSONs can contain thousands of shapes. Hide overlays/grid while dragging, collapse groups, and save projects often.\n\n" +
                    "Native app opens the wrong folder:\n" +
                    "Check the app-root line in the log. It should point at the KloudysFH6Painter folder inside the standalone."),
            _ =>
                new TutorialTopic(
                    "Start here",
                    "The safest basic workflow.",
                    "1. Prepare a clean transparent source image.\n" +
                    "2. Generate a vinyl or choose an existing JSON.\n" +
                    "3. Open the JSON in the editor if it needs cleanup or hand-made details.\n" +
                    "4. Export the editor JSON back into the app.\n" +
                    "5. Open a fresh saved/reopened game template.\n" +
                    "6. Import the selected JSON.\n" +
                    "7. Save and reload in-game to verify the final vinyl.\n\n" +
                    "Recommended direction:\n" +
                    "Generate gives you a strong first pass. The editor is where you make the vinyl intentional.")
        };
    }

    private void TutorialSearchTextChanged(object sender, TextChangedEventArgs e)
    {
        var query = (sender as TextBox)?.Text?.Trim() ?? "";
        foreach (var button in TutorialTopicButtons())
        {
            var text = $"{button.Content} {button.Tag}".ToLowerInvariant();
            button.Visibility = string.IsNullOrWhiteSpace(query) || text.Contains(query.ToLowerInvariant())
                ? Visibility.Visible
                : Visibility.Collapsed;
        }
    }

    private IEnumerable<Button> TutorialTopicButtons()
    {
        var names = new[]
        {
            "HelpTopicWorkflow",
            "HelpTopicGenerate",
            "HelpTopicImages",
            "HelpTopicJson",
            "HelpTopicEditor",
            "HelpTopicTransfer",
            "HelpTopicReports",
            "HelpTopicSetup",
            "HelpTopicTroubleshooting"
        };

        foreach (var name in names)
        {
            var button = FindControl<Button>(name);
            if (button != null)
            {
                yield return button;
            }
        }
    }

    private sealed record TutorialTopic(string Title, string Summary, string Body);

    private void PreviewLocalReport(object sender, RoutedEventArgs e)
    {
        var preview = FindControl<TextBox>("ReportPreviewTextBox");
        if (preview != null)
        {
            preview.Text = BuildLocalReport();
        }
        ShowView("Bug Reports", BugReportsView);
        Log("Local report preview updated.");
    }

    private void SaveLocalReport(object sender, RoutedEventArgs e)
    {
        try
        {
            var reportsRoot = Path.Combine(_appRoot, "runtime", "bug-reports");
            Directory.CreateDirectory(reportsRoot);
            var safeTitle = SanitizeFilePart(FindControl<TextBox>("ReportTitleTextBox")?.Text ?? "");
            if (string.IsNullOrWhiteSpace(safeTitle) || string.Equals(safeTitle, "Title", StringComparison.OrdinalIgnoreCase))
            {
                safeTitle = "kfps-report";
            }

            var path = Path.Combine(reportsRoot, $"{DateTime.UtcNow:yyyyMMdd-HHmmss}-{safeTitle}.md");
            var report = BuildLocalReport();
            File.WriteAllText(path, report, Encoding.UTF8);
            var preview = FindControl<TextBox>("ReportPreviewTextBox");
            if (preview != null)
            {
                preview.Text = report;
            }
            Log($"Saved local report: {path}");
        }
        catch (Exception ex)
        {
            Log($"Failed to save local report: {ex.Message}");
        }
    }

    private string BuildLocalReport()
    {
        var reportTypeCombo = FindControl<ComboBox>("ReportTypeComboBox");
        var reportTitleText = FindControl<TextBox>("ReportTitleTextBox");
        var reportDetailsText = FindControl<TextBox>("ReportDetailsTextBox");
        var includeContext = FindControl<CheckBox>("ReportIncludeContextCheckBox");
        var includePaths = FindControl<CheckBox>("ReportIncludePathsCheckBox");
        var includeLog = FindControl<CheckBox>("ReportIncludeLogCheckBox");
        var type = reportTypeCombo?.SelectedItem is ComboBoxItem item ? item.Content?.ToString() ?? "Bug" : "Bug";
        var titleText = reportTitleText?.Text ?? "";
        var detailText = reportDetailsText?.Text ?? "";
        var title = string.IsNullOrWhiteSpace(titleText) ? "Untitled" : titleText.Trim();
        var details = string.IsNullOrWhiteSpace(detailText) ? "(No details entered.)" : detailText.Trim();
        var theme = ThemeComboBox.SelectedItem is ThemeDefinition selectedTheme ? selectedTheme.Name : "unknown";
        var builder = new StringBuilder();
        builder.AppendLine("# KFPS Report");
        builder.AppendLine();
        builder.AppendLine($"Type: {type}");
        builder.AppendLine($"Title: {title}");
        builder.AppendLine($"Created UTC: {DateTime.UtcNow:yyyy-MM-ddTHH:mm:ssZ}");
        builder.AppendLine();
        builder.AppendLine("## User Description");
        builder.AppendLine(details);
        if (includeContext?.IsChecked == true)
        {
            builder.AppendLine();
            builder.AppendLine("## App Context");
            builder.AppendLine($"Version: {ReadVersion()}");
            builder.AppendLine($"Theme: {theme}");
            builder.AppendLine($"Platform: {Environment.OSVersion.Platform}");
        }
        if (includePaths?.IsChecked == true)
        {
            builder.AppendLine();
            builder.AppendLine("## Local Paths");
            builder.AppendLine($"App root: {_appRoot}");
            if (!string.IsNullOrWhiteSpace(_selectedSourceImage))
            {
                builder.AppendLine($"Selected source image: {_selectedSourceImage}");
            }
            if (!string.IsNullOrWhiteSpace(_selectedJson))
            {
                builder.AppendLine($"Selected JSON: {_selectedJson}");
            }
        }
        if (includeLog?.IsChecked == true)
        {
            builder.AppendLine();
            builder.AppendLine("## Visible Log");
            builder.AppendLine("```text");
            builder.AppendLine(LogBox.Text.Trim());
            builder.AppendLine("```");
        }
        builder.AppendLine();
        builder.AppendLine("## Privacy Notes");
        builder.AppendLine("This report was generated locally. No automatic upload was performed.");
        return builder.ToString();
    }

    private string ReadVersion()
    {
        var path = Path.Combine(_appRoot, "VERSION");
        return File.Exists(path) ? File.ReadAllText(path).Trim() : "unknown";
    }

    private static string SanitizeFilePart(string value)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string((value ?? "").Select(ch => invalid.Contains(ch) ? '-' : ch).ToArray()).Trim();
        return cleaned.Length > 80 ? cleaned[..80] : cleaned;
    }

    private T? FindControl<T>(string name) where T : FrameworkElement
    {
        return FindName(name) as T ?? FindVisualChildByName<T>(this, name);
    }

    private static T? FindVisualChildByName<T>(DependencyObject parent, string name) where T : FrameworkElement
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            if (child is T element && element.Name == name)
            {
                return element;
            }

            var nested = FindVisualChildByName<T>(child, name);
            if (nested != null)
            {
                return nested;
            }
        }

        return null;
    }

    private static T? FindVisualChild<T>(DependencyObject parent) where T : DependencyObject
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            if (child is T element)
            {
                return element;
            }

            var nested = FindVisualChild<T>(child);
            if (nested != null)
            {
                return nested;
            }
        }

        return null;
    }

    private static T? FindVisualParent<T>(DependencyObject? child) where T : DependencyObject
    {
        while (child != null)
        {
            if (child is T match)
            {
                return match;
            }

            child = VisualTreeHelper.GetParent(child);
        }

        return null;
    }

    private void ClearLog(object sender, RoutedEventArgs e) => LogBox.Clear();

    private void TitleBar_MouseLeftButtonDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (e.ClickCount == 2)
        {
            ToggleWindowState();
            return;
        }

        try
        {
            DragMove();
        }
        catch
        {
            // DragMove can throw if the mouse button state changes mid-drag.
        }
    }

    private void MinimizeWindow(object sender, RoutedEventArgs e)
    {
        WindowState = WindowState.Minimized;
    }

    private void MaximizeRestoreWindow(object sender, RoutedEventArgs e)
    {
        ToggleWindowState();
    }

    private void CloseWindow(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private void ToggleWindowState()
    {
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
    }

    private void RunDetached(string relativeBatch)
    {
        var path = Path.Combine(_appRoot, relativeBatch);
        if (!File.Exists(path))
        {
            Log($"Missing helper: {path}");
            return;
        }

        RunDetached("cmd.exe", $"/c \"{path}\"", _appRoot);
    }

    private void RunDetached(string fileName, string arguments, string workingDirectory)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = true
            };
            Process.Start(startInfo);
            Log($"Started: {fileName} {arguments}");
        }
        catch (Exception ex)
        {
            Log($"Failed to start {fileName}: {ex.Message}");
        }
    }

    private void RunHidden(string fileName, string arguments, string workingDirectory)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            Process.Start(startInfo);
            Log($"Started hidden: {fileName} {arguments}");
        }
        catch (Exception ex)
        {
            Log($"Failed to start hidden process {fileName}: {ex.Message}");
        }
    }

    private void RunHiddenDetached(string fileName, string arguments, string workingDirectory)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(startInfo);
            Log($"Started hidden: {fileName} {arguments}");
        }
        catch (Exception ex)
        {
            Log($"Failed to start hidden process {fileName}: {ex.Message}");
        }
    }

    private void OpenFolder(string folder)
    {
        try
        {
            Directory.CreateDirectory(folder);
            Process.Start(new ProcessStartInfo
            {
                FileName = folder,
                UseShellExecute = true
            });
            Log($"Opened folder: {folder}");
        }
        catch (Exception ex)
        {
            Log($"Failed to open folder {folder}: {ex.Message}");
        }
    }

    private void Log(string message, bool updateStatus = true)
    {
        var line = HasLeadingTimestamp(message) ? message : $"[{DateTime.Now:HH:mm:ss}] {message}";
        LogBox.AppendText(line + Environment.NewLine);
        LogBox.ScrollToEnd();
        if (updateStatus)
        {
            StatusText.Text = message.Length > 110 ? message[..110] + "..." : message;
        }
    }

    private static bool HasLeadingTimestamp(string message)
    {
        return message.Length >= 10 &&
               message[0] == '[' &&
               char.IsDigit(message[1]) &&
               char.IsDigit(message[2]) &&
               message[3] == ':' &&
               char.IsDigit(message[4]) &&
               char.IsDigit(message[5]) &&
               message[6] == ':' &&
               char.IsDigit(message[7]) &&
               char.IsDigit(message[8]) &&
               (message[9] == ']' || message[9] == '.');
    }

    private static string Quote(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "\"\"";
        }

        var builder = new StringBuilder(value.Length + 2);
        builder.Append('"');
        builder.Append(value.Replace("\"", "\\\""));
        builder.Append('"');
        return builder.ToString();
    }

    private sealed record ThemeDefinition(
        string Name,
        string BackgroundA,
        string BackgroundB,
        string BackgroundC,
        string Ink,
        string MutedInk,
        string DimInk,
        string Panel,
        string PanelSoft,
        string PanelLift,
        string Control,
        string Accent,
        string AccentDeep,
        string AccentGlow,
        string Border)
    {
        public override string ToString() => Name;
    }

    private sealed class ShellSettings
    {
        public string? ThemeName { get; set; }
        public bool EnableManualOverrides { get; set; }
    }

    private sealed record SetupReport(bool PythonPresent, bool Ready, string Message);

    private sealed record JsonSourceDefinition(string Name, string GroupTitle, string Root, bool IsGenerated);

    private sealed record JsonBrowserGroup(string Name, string FullPath, List<JsonBrowserFile> JsonFiles, DateTime Modified)
    {
        public string Display => $"{Name}  ({JsonFiles.Count})";
        public override string ToString() => $"{Name}  ({JsonFiles.Count})";
    }

    private sealed record JsonBrowserFile(string FullPath, string Name, DateTime Modified)
    {
        public string Display => $"{Name}  ({Modified:MM-dd HH:mm})";
        public override string ToString() => $"{Name}  ({Modified:MM-dd HH:mm})";
    }

    private sealed record EditorProjectItem(string Name, string FullPath, DateTime Modified, bool IsFolder)
    {
        public string Display => $"{(IsFolder ? "Folder" : "Project")}  {Name}  ({Modified:MM-dd HH:mm})";
        public override string ToString() => Display;
    }

    private sealed record RecentFileItem(string Path, string Name, DateTime Modified)
    {
        public override string ToString()
        {
            var kind = Path.EndsWith(".json", StringComparison.OrdinalIgnoreCase) ? "JSON" : "PNG";
            return $"{kind}  {Name}  ({Modified:MM-dd HH:mm})";
        }
    }
}
