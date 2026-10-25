using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace MainBrain.Desktop.Controls;

/// <summary>
/// Futūristisks Matrix lietus + lidojoši simboli fonā.
/// </summary>
public sealed class MatrixRainCanvas : FrameworkElement
{
    private readonly DispatcherTimer _timer;
    private readonly List<Drop> _drops = new();
    private readonly List<Floater> _floaters = new();
    private readonly Random _rng = new();
    private readonly Typeface _typeface = new("Consolas");
    private Size _size;
    private bool _initialized;

    private static readonly char[] Glyphs =
        "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789ABCDEF<>{}[]/*+-=$#@%&ΞΨΩλμπαβγδΣ".ToCharArray();

    public MatrixRainCanvas()
    {
        IsHitTestVisible = false;
        SnapsToDevicePixels = true;
        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(33) };
        _timer.Tick += (_, _) =>
        {
            Tick();
            InvalidateVisual();
        };
        Loaded += (_, _) =>
        {
            Init();
            _timer.Start();
        };
        Unloaded += (_, _) => _timer.Stop();
        SizeChanged += (_, e) =>
        {
            _size = e.NewSize;
            Init(force: true);
        };
    }

    private void Init(bool force = false)
    {
        if (_size.Width < 10 || _size.Height < 10)
        {
            return;
        }

        if (_initialized && !force)
        {
            return;
        }

        _drops.Clear();
        _floaters.Clear();
        var cols = Math.Max(12, (int)(_size.Width / 18));
        for (var i = 0; i < cols; i++)
        {
            _drops.Add(NewDrop(i * 18 + _rng.NextDouble() * 6, spawnTop: true));
        }

        for (var i = 0; i < 40; i++)
        {
            _floaters.Add(NewFloater());
        }

        _initialized = true;
    }

    private Drop NewDrop(double x, bool spawnTop)
    {
        var len = _rng.Next(8, 22);
        var chars = new char[len];
        for (var i = 0; i < len; i++)
        {
            chars[i] = Glyphs[_rng.Next(Glyphs.Length)];
        }

        return new Drop
        {
            X = x,
            Y = spawnTop ? -_rng.Next(0, (int)_size.Height) : -_rng.Next(40, 400),
            Speed = 2.2 + _rng.NextDouble() * 6.5,
            Chars = chars,
            Head = 0,
        };
    }

    private Floater NewFloater()
    {
        return new Floater
        {
            X = _rng.NextDouble() * Math.Max(1, _size.Width),
            Y = _rng.NextDouble() * Math.Max(1, _size.Height),
            Vx = (_rng.NextDouble() - 0.5) * 1.8,
            Vy = (_rng.NextDouble() - 0.5) * 1.2,
            Char = Glyphs[_rng.Next(Glyphs.Length)],
            Size = 10 + _rng.NextDouble() * 16,
            Alpha = 0.15 + _rng.NextDouble() * 0.55,
            Spin = (_rng.NextDouble() - 0.5) * 0.12,
            Angle = _rng.NextDouble() * Math.PI * 2,
        };
    }

    private void Tick()
    {
        if (!_initialized)
        {
            return;
        }

        foreach (var d in _drops)
        {
            d.Y += d.Speed;
            d.Head++;
            if (d.Head % 2 == 0)
            {
                d.Chars[_rng.Next(d.Chars.Length)] = Glyphs[_rng.Next(Glyphs.Length)];
            }

            if (d.Y - d.Chars.Length * 16 > _size.Height)
            {
                var idx = _drops.IndexOf(d);
                _drops[idx] = NewDrop(d.X, spawnTop: true);
            }
        }

        foreach (var f in _floaters)
        {
            f.X += f.Vx;
            f.Y += f.Vy;
            f.Angle += f.Spin;
            if (f.X < -20 || f.X > _size.Width + 20 || f.Y < -20 || f.Y > _size.Height + 20)
            {
                f.X = _rng.NextDouble() * _size.Width;
                f.Y = _rng.NextDouble() * _size.Height;
                f.Char = Glyphs[_rng.Next(Glyphs.Length)];
            }
        }
    }

    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc);
        if (_size.Width < 1 || _size.Height < 1)
        {
            return;
        }

        dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(2, 6, 8)), null, new Rect(_size));

        foreach (var d in _drops)
        {
            for (var i = 0; i < d.Chars.Length; i++)
            {
                var y = d.Y - i * 16;
                if (y < -20 || y > _size.Height + 20)
                {
                    continue;
                }

                var t = 1.0 - i / (double)d.Chars.Length;
                var g = (byte)(40 + 200 * t);
                var brush = i == 0
                    ? new SolidColorBrush(Color.FromArgb(240, 180, 255, 200))
                    : new SolidColorBrush(Color.FromArgb((byte)(40 + 180 * t), 0, g, (byte)(g * 0.55)));
                var ft = new FormattedText(
                    d.Chars[i].ToString(),
                    CultureInfo.InvariantCulture,
                    FlowDirection.LeftToRight,
                    _typeface,
                    14,
                    brush,
                    VisualTreeHelper.GetDpi(this).PixelsPerDip);
                dc.DrawText(ft, new Point(d.X, y));
            }
        }

        foreach (var f in _floaters)
        {
            var brush = new SolidColorBrush(Color.FromArgb((byte)(f.Alpha * 255), 0, 255, 140));
            dc.PushTransform(new RotateTransform(f.Angle * 180 / Math.PI, f.X, f.Y));
            var ft = new FormattedText(
                f.Char.ToString(),
                CultureInfo.InvariantCulture,
                FlowDirection.LeftToRight,
                _typeface,
                f.Size,
                brush,
                VisualTreeHelper.GetDpi(this).PixelsPerDip);
            dc.DrawText(ft, new Point(f.X, f.Y));
            dc.Pop();
        }
    }

    private sealed class Drop
    {
        public double X;
        public double Y;
        public double Speed;
        public char[] Chars = Array.Empty<char>();
        public int Head;
    }

    private sealed class Floater
    {
        public double X;
        public double Y;
        public double Vx;
        public double Vy;
        public char Char;
        public double Size;
        public double Alpha;
        public double Spin;
        public double Angle;
    }
}
