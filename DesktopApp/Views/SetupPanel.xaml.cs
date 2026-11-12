using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using FlowShield.Services;
using FlowShield.ViewModels;
using Image = System.Windows.Controls.Image;
using Point = System.Windows.Point;
using Size = System.Windows.Size;

namespace FlowShield.Views;

/// <summary>
/// The setup panel's behaviour (#431): focus in and out, Esc and a click
/// outside, and its acrylic.
///
/// WPF has no backdrop blur, so acrylic is built the way the redesign README
/// describes: one snapshot of the page under the panel, blurred once into a
/// static bitmap under the 74% <c>Acrylic</c> tint. Nothing is blurred live:
/// the blur runs once per snapshot, in software, and the panel then shows a
/// plain image. The snapshot is re-taken when the panel opens, when it or the
/// window changes size, when the theme changes and when what Today shows
/// beneath it changes, each debounced. It is only used while the window's
/// backdrop is Mica (<see cref="AcrylicAllowed"/>); with transparency effects
/// off, on battery saver, on Windows 10, in software rendering or while the
/// window is inactive, the panel is the solid E3 surface underneath.
/// </summary>
public partial class SetupPanel : UserControl
{
    /// <summary>The blur radius, from the redesign's depth table.</summary>
    public const double BlurRadius = 28;

    /// <summary>
    /// The page drawn under the panel: the title and the page host, not the
    /// panel itself. Set by MainWindow.
    /// </summary>
    public FrameworkElement? Backdrop { get; set; }

    /// <summary>Raised when the panel closes, so the caller can put focus back on Set up.</summary>
    public event EventHandler? Closed;

    private bool _acrylicAllowed;
    /// <summary>The window's backdrop is Mica, so translucency is on (Part A, Depth: Fallback).</summary>
    public bool AcrylicAllowed
    {
        get => _acrylicAllowed;
        set
        {
            if (_acrylicAllowed == value) return;
            _acrylicAllowed = value;
            ScheduleSnapshot();
        }
    }

    /// <summary>Whether the last snapshot drew acrylic, for the log and tests.</summary>
    public bool ShowingAcrylic => AcrylicLayer.Visibility == Visibility.Visible;

    private readonly DispatcherTimer _snapshotTimer;

    public SetupPanel()
    {
        InitializeComponent();
        _snapshotTimer = new DispatcherTimer(DispatcherPriority.Background) { Interval = TimeSpan.FromMilliseconds(120) };
        _snapshotTimer.Tick += (_, _) =>
        {
            _snapshotTimer.Stop();
            TakeSnapshot();
        };
        ThemeService.Changed += OnThemeChanged;
        Unloaded += (_, _) => ThemeService.Changed -= OnThemeChanged;
        DataContextChanged += OnDataContextChanged;
    }

    private void OnThemeChanged(object? sender, EventArgs e) => ScheduleSnapshot();

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (e.OldValue is INotifyPropertyChanged old) old.PropertyChanged -= OnViewModelChanged;
        if (e.NewValue is INotifyPropertyChanged now) now.PropertyChanged += OnViewModelChanged;
    }

    /// <summary>What Today shows under the panel moves as choices are made.</summary>
    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        switch (e.PropertyName)
        {
            case nameof(TodayViewModel.SprintOptionsSummary):
            case nameof(TodayViewModel.ProfileCaption):
            case nameof(TodayViewModel.RemainingText):
            case nameof(TodayViewModel.SelectedShield):
                ScheduleSnapshot();
                break;
        }
    }

    private void OnIsVisibleChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (IsVisible)
        {
            TakeSnapshot();
            // Focus into the panel, on the length that is picked, as a
            // flyout does; Tab then cycles inside it.
            Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
            {
                var target = FindChecked(Panel) ?? (IInputElement)CloseButton;
                Keyboard.Focus(target);
            });
        }
        else
        {
            _snapshotTimer.Stop();
            AcrylicImage.Source = null;
            Closed?.Invoke(this, EventArgs.Empty);
        }
    }

    private static IInputElement? FindChecked(DependencyObject root)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is RadioButton { IsChecked: true, IsVisible: true } radio) return radio;
            if (FindChecked(child) is { } found) return found;
        }
        return null;
    }

    private void Close()
    {
        if (DataContext is TodayViewModel vm) vm.CloseSprintOptions();
    }

    private void OnOutsideMouseDown(object sender, MouseButtonEventArgs e)
    {
        Close();
        e.Handled = true;
    }

    private void OnPanelKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Escape) return;
        // A dropdown that is open takes Esc for itself first.
        if (Keyboard.FocusedElement is ComboBoxItem || (e.OriginalSource as DependencyObject) is ComboBox { IsDropDownOpen: true })
            return;
        Close();
        e.Handled = true;
    }

    private void OnPanelSizeChanged(object sender, SizeChangedEventArgs e)
    {
        AcrylicLayer.Clip = new RectangleGeometry(new Rect(0, 0, e.NewSize.Width, e.NewSize.Height), 12, 12);
        ScheduleSnapshot();
    }

    /// <summary>Called by MainWindow when the window or page changes size.</summary>
    public void ScheduleSnapshot()
    {
        if (!IsVisible) return;
        _snapshotTimer.Stop();
        _snapshotTimer.Start();
    }

    /// <summary>
    /// Draws the page beneath the panel, blurred, into one frozen bitmap. The
    /// snapshot reaches past the panel by one and a half blur radii on every
    /// side, so the blur's edges fade from real content, not from nothing.
    /// </summary>
    private void TakeSnapshot()
    {
        if (!IsVisible || !_acrylicAllowed || Backdrop is not { } page || page.ActualWidth < 1 || Panel.ActualWidth < 1)
        {
            AcrylicLayer.Visibility = Visibility.Collapsed;
            AcrylicImage.Source = null;
            return;
        }

        try
        {
            var clock = Stopwatch.StartNew();
            var dpi = VisualTreeHelper.GetDpi(this);
            var pad = Math.Ceiling(BlurRadius * 1.5);
            var origin = Panel.TranslatePoint(new Point(0, 0), page);
            var area = new Rect(origin.X - pad, origin.Y - pad, Panel.ActualWidth + 2 * pad, Panel.ActualHeight + 2 * pad);
            var pixelWidth = (int)Math.Ceiling(area.Width * dpi.DpiScaleX);
            var pixelHeight = (int)Math.Ceiling(area.Height * dpi.DpiScaleY);

            // The page region, through a VisualBrush, so its place in the
            // window doesn't shift what RenderTargetBitmap draws.
            var region = new DrawingVisual();
            using (var dc = region.RenderOpen())
            {
                var brush = new VisualBrush(page)
                {
                    Viewbox = area,
                    ViewboxUnits = BrushMappingMode.Absolute,
                    Stretch = Stretch.Fill,
                };
                dc.DrawRectangle(brush, null, new Rect(0, 0, area.Width, area.Height));
            }
            var sharp = new RenderTargetBitmap(pixelWidth, pixelHeight, 96 * dpi.DpiScaleX, 96 * dpi.DpiScaleY, PixelFormats.Pbgra32);
            sharp.Render(region);
            sharp.Freeze();

            // Blurred once, here, into a second bitmap.
            var image = new Image
            {
                Source = sharp,
                Width = area.Width,
                Height = area.Height,
                Effect = new BlurEffect { Radius = BlurRadius, KernelType = KernelType.Gaussian, RenderingBias = RenderingBias.Performance },
            };
            image.Measure(new Size(area.Width, area.Height));
            image.Arrange(new Rect(0, 0, area.Width, area.Height));
            var blurred = new RenderTargetBitmap(pixelWidth, pixelHeight, 96 * dpi.DpiScaleX, 96 * dpi.DpiScaleY, PixelFormats.Pbgra32);
            blurred.Render(image);
            blurred.Freeze();

            AcrylicImage.Source = blurred;
            AcrylicImage.Width = area.Width;
            AcrylicImage.Height = area.Height;
            AcrylicImage.Margin = new Thickness(-pad, -pad, 0, 0);
            AcrylicLayer.Visibility = Visibility.Visible;
            if (clock.ElapsedMilliseconds > 150)
                Log.Info($"setup panel: acrylic snapshot took {clock.ElapsedMilliseconds} ms");
        }
        catch (Exception ex)
        {
            // Solid E3 is the fallback, and it is always there underneath.
            AcrylicLayer.Visibility = Visibility.Collapsed;
            AcrylicImage.Source = null;
            Log.Warn($"setup panel: acrylic snapshot failed, solid E3 instead: {ex.Message}");
        }
    }
}
