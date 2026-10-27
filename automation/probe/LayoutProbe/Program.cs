using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using FlowShield.Models;
using FlowShield.Services;
using FlowShield.ViewModels;
using FlowShield.Views;

// FlowShield's global usings include System.Drawing; keep the rendered brush WPF's.
using Application = System.Windows.Application;
using Brush = System.Windows.Media.Brush;
using WpfPanel = System.Windows.Controls.Panel;

namespace LayoutProbe;

internal sealed record ProbeOptions(
    int Width,
    int Height,
    string Label,
    string Theme,
    string OutputDirectory,
    string[] Pages,
    double Scale);

internal static class Program
{
    private static ProbeOptions? _options;

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            _options = Parse(args);
            Directory.CreateDirectory(_options.OutputDirectory);

            using var instance = SingleInstance.TryAcquire();
            if (instance is null)
                throw new InvalidOperationException(
                    "FlowShield is already running; close it before using LayoutProbe.");

            var app = new FlowShield.App { Instance = instance, ShutdownMode = ShutdownMode.OnExplicitShutdown };
            var runner = new ProbeRunner(app);
            app.Startup += (_, _) => app.Dispatcher.BeginInvoke(
                new Action(runner.BeginCapture), DispatcherPriority.Send);
            app.InitializeComponent();
            app.Run();
            return Environment.ExitCode;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"{ex.GetType().Name}: {ex.Message}");
            return 1;
        }
    }

    private static ProbeOptions Parse(string[] args)
    {
        var width = 1536;
        var height = 824;
        var label = "capture";
        var theme = "dark";
        var outputDirectory = Path.Combine(Environment.CurrentDirectory, "layout-probe-output");
        var pages = new[] { "today-rest", "history", "blocked-apps", "schedule", "settings-top" };
        var scale = 1d;

        for (var i = 0; i < args.Length; i++)
        {
            string Value(string option)
            {
                if (i + 1 >= args.Length) throw new ArgumentException($"{option} needs a value");
                return args[++i];
            }

            if (args[i] == "--size")
            {
                var parts = Value(args[i]).Split('x', 'X');
                if (parts.Length != 2 || !int.TryParse(parts[0], out width)
                    || !int.TryParse(parts[1], out height) || width <= 0 || height <= 0)
                    throw new ArgumentException("--size must be WIDTHxHEIGHT in DIPs");
            }
            else if (args[i].StartsWith("--size=", StringComparison.OrdinalIgnoreCase))
            {
                var parts = args[i][7..].Split('x', 'X');
                if (parts.Length != 2 || !int.TryParse(parts[0], out width)
                    || !int.TryParse(parts[1], out height) || width <= 0 || height <= 0)
                    throw new ArgumentException("--size must be WIDTHxHEIGHT in DIPs");
            }
            else if (args[i] == "--label") label = Value(args[i]);
            else if (args[i] == "--theme") theme = Value(args[i]).ToLowerInvariant();
            else if (args[i] == "--out") outputDirectory = Value(args[i]);
            else if (args[i] == "--pages")
                pages = Value(args[i]).Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            else if (args[i] == "--scale" && !double.TryParse(Value(args[i]), out scale))
                throw new ArgumentException("--scale must be a number");
            else if (args[i].StartsWith("--scale=", StringComparison.OrdinalIgnoreCase)
                     && !double.TryParse(args[i][8..], out scale))
                throw new ArgumentException("--scale must be a number");
        }

        if (theme is not ("dark" or "light")) throw new ArgumentException("--theme must be dark or light");
        if (!double.IsFinite(scale) || scale <= 0 || scale > 4) throw new ArgumentException("--scale must be in (0, 4]");
        if (pages.Length == 0) throw new ArgumentException("--pages must contain at least one page");

        return new ProbeOptions(width, height, label, theme, Path.GetFullPath(outputDirectory), pages, scale);
    }

    private sealed class ProbeRunner
    {
        private readonly FlowShield.App _app;
        private FlowShield.MainWindow? _mainWindow;

        public ProbeRunner(FlowShield.App app) => _app = app;

        public void BeginCapture()
        {
            if (_app.MainWindow is not FlowShield.MainWindow sourceWindow)
            {
                Environment.ExitCode = 1;
                _app.Shutdown();
                return;
            }

            _mainWindow = sourceWindow;
            var options = _options ?? throw new InvalidOperationException("probe options were not parsed");

            // Keep the actual app window offscreen. Render a second MainWindow
            // instance with the same real view model, but leave it unshown so
            // its WPF visual tree has no monitor-sized HWND clip.
            sourceWindow.ShowInTaskbar = false;
            sourceWindow.ShowActivated = false;
            HookMaxTrackSize(sourceWindow);
            sourceWindow.Hide();
            sourceWindow.Left = -40000;
            sourceWindow.Top = -40000;

            var renderWindow = new FlowShield.MainWindow
            {
                DataContext = _app.ViewModel,
                Width = options.Width,
                Height = options.Height,
                WindowStyle = WindowStyle.None,
                ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false,
                ShowActivated = false,
            };
            renderWindow.MinWidth = 0;
            renderWindow.MinHeight = 0;
            renderWindow.MaxWidth = 32767;
            renderWindow.MaxHeight = 32767;

            _app.Dispatcher.BeginInvoke(new Action(() => CaptureAndExit(renderWindow)),
                DispatcherPriority.ApplicationIdle);
        }

        private async void CaptureAndExit(Window window)
        {
            try
            {
                await CaptureAsync(window);
                Environment.ExitCode = 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"{ex.GetType().Name}: {ex.Message}");
                Environment.ExitCode = 1;
            }
            finally
            {
                // MainWindow normally hides to the tray on close. This process is
                // only a renderer, so let App.Shutdown close it and dispose its tray.
                typeof(FlowShield.MainWindow)
                    .GetField("_reallyClosing", BindingFlags.Instance | BindingFlags.NonPublic)
                    ?.SetValue(_mainWindow, true);
                typeof(FlowShield.MainWindow)
                    .GetField("_reallyClosing", BindingFlags.Instance | BindingFlags.NonPublic)
                    ?.SetValue(window, true);
                if (!ReferenceEquals(window, _mainWindow)) window.Close();
                _app.Shutdown();
            }
        }

        private async Task CaptureAsync(Window window)
        {
            var options = _options ?? throw new InvalidOperationException("probe options were not parsed");
            var viewModel = DataContextOf(window)
                ?? throw new InvalidOperationException("MainWindow has no MainViewModel");

            ThemeService.Apply(options.Theme == "light" ? AppTheme.Light : AppTheme.Dark);
            await WaitForLayout(window);
            await LayoutRoot(window, options.Width, options.Height);
            VerifyRootSize(window, options.Width, options.Height);

            foreach (var page in options.Pages)
            {
                await SelectPage(window, viewModel, page);
                await WaitForLayout(window);
                await LayoutRoot(window, options.Width, options.Height);
                if (page.StartsWith("settings-", StringComparison.Ordinal))
                {
                    await window.Dispatcher.InvokeAsync(() =>
                    {
                        // An unshown Window has no Loaded event. Settings uses
                        // that event to choose its responsive rail and dev fields.
                        if (FindVisual<SettingsView>(window.Content as DependencyObject) is { } settingsView)
                            settingsView.RaiseEvent(new RoutedEventArgs(FrameworkElement.LoadedEvent, settingsView));
                        window.UpdateLayout();
                    }, DispatcherPriority.ApplicationIdle);
                    await LayoutRoot(window, options.Width, options.Height);
                }
                VerifyRootSize(window, options.Width, options.Height);

                var root = window.Content as FrameworkElement
                    ?? throw new InvalidOperationException("MainWindow has no FrameworkElement content");
                SaveImage(root, AppBackground() ?? window.Background,
                    page, options.Width, options.Height, options.Scale);

                if (page == "settings-top")
                {
                    var settingsView = FindVisual<SettingsView>(root)
                        ?? throw new InvalidOperationException("SettingsView was not found");
                    var settingsScroll = FindVisual<ScrollViewer>(settingsView)
                        ?? throw new InvalidOperationException("Settings ScrollViewer was not found");
                    SaveFullScroll(settingsScroll, "settings-full", page, options.Width, options.Height, options.Scale);
                }
                else if (page is not ("settings-license" or "settings-focus" or "settings-app"
                                      or "settings-notifications" or "settings-data" or "settings-about"
                                      or "lock-screen" or "first-run-welcome"))
                {
                    var scroll = FindScrollableViewer(FindVisiblePage(root));
                    if (scroll is not null)
                        SaveFullScroll(scroll, $"{page}-full", page, options.Width, options.Height, options.Scale);
                }
            }
        }

        private static MainViewModel? DataContextOf(Window window) => window.DataContext as MainViewModel;

        private static async Task SelectPage(Window window, MainViewModel viewModel, string page)
        {
            switch (page)
            {
                case "today-rest":
                case "today-sprint":
                    viewModel.NavigateCommand.Execute(AppPage.Today);
                    if (page == "today-sprint")
                    {
                        viewModel.Today.SelectedMinutes = 15;
                        viewModel.Today.IntentionText = "Finish the essay conclusion";
                        viewModel.Today.StartCommand.Execute(null);
                        if (!viewModel.Today.IsRunning)
                            throw new InvalidOperationException("Today sprint did not start");
                    }
                    break;
                case "history":
                    viewModel.NavigateCommand.Execute(AppPage.History);
                    break;
                case "blocked-apps":
                    viewModel.NavigateCommand.Execute(AppPage.BlockedApps);
                    break;
                case "schedule":
                case "sleep-blocking":
                    viewModel.NavigateCommand.Execute(AppPage.SleepBlocking);
                    break;
                case "settings-top":
                    viewModel.NavigateCommand.Execute(AppPage.Settings);
                    break;
                case "settings-license":
                case "settings-focus":
                case "settings-app":
                case "settings-notifications":
                case "settings-data":
                case "settings-about":
                    viewModel.NavigateCommand.Execute(AppPage.Settings);
                    break;
                case "lock-screen":
                    if (!viewModel.IsLocked) throw new InvalidOperationException(
                        "lock-screen requested without --expire-trial");
                    break;
                case "first-run-welcome":
                    if (!viewModel.FirstRun.IsVisible) throw new InvalidOperationException(
                        "first-run-welcome requested without an unfinished first run");
                    break;
                default:
                    throw new ArgumentException($"unknown page '{page}'");
            }

            await window.Dispatcher.InvokeAsync(() =>
            {
                if (page is "settings-license" or "settings-focus" or "settings-app"
                    or "settings-notifications" or "settings-data" or "settings-about")
                {
                    var settingsView = FindVisual<SettingsView>(window.Content as DependencyObject)
                        ?? throw new InvalidOperationException("SettingsView was not found");
                    var section = page switch
                    {
                        "settings-license" => "Licence",
                        "settings-focus" => "Focus",
                        "settings-app" => "App",
                        "settings-notifications" => "Notifications",
                        "settings-data" => "Data",
                        _ => "About",
                    };
                    settingsView.JumpTo(section);
                }
                else if (page == "settings-top")
                {
                    var settingsView = FindVisual<SettingsView>(window.Content as DependencyObject);
                    var scroll = settingsView is null ? null : FindVisual<ScrollViewer>(settingsView);
                    scroll?.ScrollToTop();
                }
                else if (window.Content is DependencyObject content
                         && FindScrollableViewer(FindVisiblePage(content)) is { } scrollViewer)
                {
                    scrollViewer.ScrollToTop();
                }
                window.UpdateLayout();
            }, DispatcherPriority.Loaded);
        }

        private static async Task WaitForLayout(Window window)
        {
            await window.Dispatcher.InvokeAsync(() =>
            {
                window.UpdateLayout();
                (window.Content as FrameworkElement)?.UpdateLayout();
            }, DispatcherPriority.ApplicationIdle);
        }

        private static async Task LayoutRoot(Window window, double width, double height)
        {
            var root = window.Content as FrameworkElement
                ?? throw new InvalidOperationException("MainWindow has no FrameworkElement content");
            await window.Dispatcher.InvokeAsync(() =>
            {
                root.Width = width;
                root.Height = height;
                root.Measure(new System.Windows.Size(width, height));
                root.Arrange(new Rect(0, 0, width, height));
                root.UpdateLayout();
            }, DispatcherPriority.ApplicationIdle);
        }

        private static void VerifyRootSize(Window window, double width, double height)
        {
            var root = window.Content as FrameworkElement
                ?? throw new InvalidOperationException("MainWindow has no FrameworkElement content");
            if (Math.Abs(root.ActualWidth - width) > 1 || Math.Abs(root.ActualHeight - height) > 1)
                throw new InvalidOperationException(
                    $"root content reached {root.ActualWidth:0.##} × {root.ActualHeight:0.##} DIP, "
                    + $"requested {width:0.##} × {height:0.##} DIP");
        }

        private void SaveImage(FrameworkElement element, Brush? background, string page,
            double requestedWidth, double requestedHeight, double scale)
        {
            var width = element.ActualWidth;
            var height = element.ActualHeight;
            if (width <= 0 || height <= 0)
                throw new InvalidOperationException($"{page} has a zero-sized render root ({width} × {height})");

            SaveBitmap(element, background, width, height, scale,
                Path.Combine(_options!.OutputDirectory,
                    $"{_options.Label}_{_options.Width}x{_options.Height}dip_{_options.Theme}_{page}.png"),
                page, requestedWidth, requestedHeight);
        }

        private void SaveFullScroll(ScrollViewer scroll, string outputPage, string sourcePage,
            double requestedWidth, double requestedHeight, double scale)
        {
            if (scroll.ScrollableHeight <= 0 || scroll.Content is not FrameworkElement content) return;
            var width = content.ActualWidth;
            var height = Math.Max(content.ActualHeight, scroll.ExtentHeight);
            if (width <= 0 || height <= 0) return;

            SaveBitmap(content, AppBackground() ?? Application.Current.MainWindow?.Background,
                width, height, scale,
                Path.Combine(_options!.OutputDirectory,
                    $"{_options.Label}_{_options.Width}x{_options.Height}dip_{_options.Theme}_{outputPage}.png"),
                outputPage, requestedWidth, requestedHeight, sourcePage);
        }

        private void SaveBitmap(FrameworkElement element, Brush? background, double width, double height, double scale,
            string file, string page, double requestedWidth, double requestedHeight, string? sourcePage = null)
        {
            var pixelWidth = checked((int)Math.Ceiling(width * scale));
            var pixelHeight = checked((int)Math.Ceiling(height * scale));
            if (pixelWidth > 32767 || pixelHeight > 32767)
                throw new InvalidOperationException($"render dimensions exceed WPF's bitmap limit: {pixelWidth} × {pixelHeight}");

            var bitmap = new RenderTargetBitmap(pixelWidth, pixelHeight, 96 * scale, 96 * scale,
                PixelFormats.Pbgra32);
            if (background is not null)
            {
                // Paint the theme brush first because a detached Window has no
                // compositor surface behind its transparent root panels.
                var backdrop = new DrawingVisual();
                using (var drawingContext = backdrop.RenderOpen())
                    drawingContext.DrawRectangle(background, null, new Rect(0, 0, width, height));
                bitmap.Render(backdrop);
            }

            // Render the real visual directly. A VisualBrush carries the
            // source HWND's monitor DPI into the target and scales the pixels
            // at 100% incorrectly on high-DPI displays.
            bitmap.Render(element);
            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using (var stream = File.Create(file)) encoder.Save(stream);

            Console.WriteLine(JsonSerializer.Serialize(new
            {
                page,
                source_page = sourcePage,
                requested = new { width = requestedWidth, height = requestedHeight },
                actual = new { width, height },
                path = Path.GetFullPath(file),
                pixel_size = new { width = pixelWidth, height = pixelHeight },
                scale,
            }));
        }

        private static Brush? AppBackground() => Application.Current?.TryFindResource("Bg") as Brush;

        private static FrameworkElement FindVisiblePage(DependencyObject root)
        {
            var pageHost = FindByName<WpfPanel>(root, "PageHost")
                ?? throw new InvalidOperationException("MainWindow page host was not found");
            return pageHost.Children.OfType<FrameworkElement>()
                .FirstOrDefault(page => page.Visibility == Visibility.Visible)
                ?? throw new InvalidOperationException("No main page is visible");
        }

        private static ScrollViewer? FindScrollableViewer(DependencyObject root) =>
            Descendants(root).OfType<ScrollViewer>()
                .FirstOrDefault(scroll => scroll.Visibility == Visibility.Visible && scroll.ScrollableHeight > 0);

        private static T? FindVisual<T>(DependencyObject? root) where T : DependencyObject =>
            root is null ? null : Descendants(root).OfType<T>().FirstOrDefault();

        private static T? FindByName<T>(DependencyObject root, string name) where T : FrameworkElement =>
            Descendants(root).OfType<T>().FirstOrDefault(element => element.Name == name);

        private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
        {
            var queue = new Queue<DependencyObject>();
            queue.Enqueue(root);
            while (queue.Count > 0)
            {
                var current = queue.Dequeue();
                yield return current;
                for (var index = 0; index < VisualTreeHelper.GetChildrenCount(current); index++)
                    queue.Enqueue(VisualTreeHelper.GetChild(current, index));
            }
        }

        private static void HookMaxTrackSize(Window window)
        {
            var hwnd = new WindowInteropHelper(window).Handle;
            var source = HwndSource.FromHwnd(hwnd)
                ?? throw new InvalidOperationException("MainWindow HwndSource is unavailable");
            source.AddHook((IntPtr hwnd, int message, IntPtr wParam, IntPtr lParam, ref bool handled) =>
            {
                if (message != WmGetMinMaxInfo || lParam == IntPtr.Zero) return IntPtr.Zero;
                var info = Marshal.PtrToStructure<MinMaxInfo>(lParam);
                info.MaxSize.X = 32767;
                info.MaxSize.Y = 32767;
                info.MaxTrackSize.X = 32767;
                info.MaxTrackSize.Y = 32767;
                Marshal.StructureToPtr(info, lParam, false);
                handled = true;
                return IntPtr.Zero;
            });
        }

        private const int WmGetMinMaxInfo = 0x0024;

        [StructLayout(LayoutKind.Sequential)]
        private struct Point { public int X; public int Y; }

        [StructLayout(LayoutKind.Sequential)]
        private struct MinMaxInfo
        {
            public Point Reserved;
            public Point MaxSize;
            public Point MaxPosition;
            public Point MinTrackSize;
            public Point MaxTrackSize;
        }

    }
}
