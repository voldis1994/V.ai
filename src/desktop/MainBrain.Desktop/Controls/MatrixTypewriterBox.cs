using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace MainBrain.Desktop.Controls;

/// <summary>
/// Chat teksts Matrix stilā — jaunās AI atbildes "ierakstās" pa simbolam.
/// </summary>
public sealed class MatrixTypewriterBox : TextBox
{
    public static readonly DependencyProperty FullTextProperty = DependencyProperty.Register(
        nameof(FullText),
        typeof(string),
        typeof(MatrixTypewriterBox),
        new PropertyMetadata("", OnFullTextChanged));

    private readonly DispatcherTimer _timer;
    private string _target = "";
    private int _index;
    private int _stableLength;

    public MatrixTypewriterBox()
    {
        IsReadOnly = true;
        AcceptsReturn = true;
        TextWrapping = TextWrapping.Wrap;
        BorderThickness = new Thickness(0);
        Background = Brushes.Transparent;
        Foreground = new SolidColorBrush(Color.FromRgb(255, 120, 210));
        FontFamily = new FontFamily("Consolas");
        FontSize = 16;
        CaretBrush = Brushes.Transparent;
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto;
        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(12) };
        _timer.Tick += (_, _) => Tick();
    }

    public string FullText
    {
        get => (string)GetValue(FullTextProperty);
        set => SetValue(FullTextProperty, value);
    }

    private static void OnFullTextChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is MatrixTypewriterBox box)
        {
            box.OnNewText(e.NewValue as string ?? "");
        }
    }

    private void OnNewText(string value)
    {
        _target = value ?? "";
        // Ja teksts tikai pieaug — typewriter tikai jaunajai daļai
        if (_target.StartsWith(Text, StringComparison.Ordinal) && Text.Length > 0)
        {
            _stableLength = Text.Length;
            _index = Text.Length;
        }
        else if (_target.Length < Text.Length || !Text.StartsWith(_target.Substring(0, Math.Min(Text.Length, _target.Length)), StringComparison.Ordinal))
        {
            // reset
            Text = "";
            _stableLength = 0;
            _index = 0;
        }

        if (_index < _target.Length)
        {
            _timer.Start();
        }
    }

    private void Tick()
    {
        if (_index >= _target.Length)
        {
            _timer.Stop();
            Text = _target;
            ScrollToEnd();
            return;
        }

        // burst a few chars for snappier feel
        var step = Math.Min(3, _target.Length - _index);
        _index += step;
        Text = _target[.._index];
        // occasional glyph flicker on the newest char
        if (_index > _stableLength && _index < _target.Length && (_index % 7 == 0))
        {
            // visual already green; keep moving
        }

        ScrollToEnd();
    }
}
