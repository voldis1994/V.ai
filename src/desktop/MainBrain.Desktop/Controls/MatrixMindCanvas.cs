using System.Globalization;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;

namespace MainBrain.Desktop.Controls;

/// <summary>
/// Dzīva Matrix sistēma: lietus + lidojoši hieroglifi, kas salido centrā un izveido atbildi.
/// </summary>
public sealed class MatrixMindCanvas : FrameworkElement
{
    public static readonly DependencyProperty AnswerTextProperty = DependencyProperty.Register(
        nameof(AnswerText),
        typeof(string),
        typeof(MatrixMindCanvas),
        new PropertyMetadata("", OnAnswerTextChanged));

    public static readonly DependencyProperty IsThinkingProperty = DependencyProperty.Register(
        nameof(IsThinking),
        typeof(bool),
        typeof(MatrixMindCanvas),
        new PropertyMetadata(false));

    public static readonly DependencyProperty StatusLineProperty = DependencyProperty.Register(
        nameof(StatusLine),
        typeof(string),
        typeof(MatrixMindCanvas),
        new PropertyMetadata(""));

    private readonly DispatcherTimer _timer;
    private readonly List<Drop> _drops = new();
    private readonly List<Floater> _floaters = new();
    private readonly List<GlyphParticle> _particles = new();
    private readonly Random _rng = new();
    private readonly Typeface _typeface = new("Consolas");
    private Size _size;
    private bool _initialized;
    private double _pulse;
    private string _forming = "";
    private double _formProgress; // 0..1
    private bool _holdingAnswer;

    private static readonly char[] Glyphs =
        "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789ABCDEF<>{}[]/*+-=$#@%&ΞΨΩλμπαβγδΣ█▓▒░".ToCharArray();

    public MatrixMindCanvas()
    {
        IsHitTestVisible = false;
        SnapsToDevicePixels = true;
        ClipToBounds = true;
        _timer = new DispatcherTimer(DispatcherPriority.Render)
        {
            Interval = TimeSpan.FromMilliseconds(16),
        };
        _timer.Tick += (_, _) =>
        {
            Tick();
            InvalidateVisual();
        };
        Loaded += (_, _) =>
        {
            if (ActualWidth > 10)
            {
                _size = new Size(ActualWidth, ActualHeight);
            }

            Init(force: true);
            _timer.Start();
        };
        Unloaded += (_, _) => _timer.Stop();
        SizeChanged += (_, e) =>
        {
            _size = e.NewSize;
            Init(force: true);
            if (!string.IsNullOrEmpty(_forming))
            {
                RebuildParticles(_forming);
            }
        };
    }

    public string AnswerText
    {
        get => (string)GetValue(AnswerTextProperty);
        set => SetValue(AnswerTextProperty, value);
    }

    public bool IsThinking
    {
        get => (bool)GetValue(IsThinkingProperty);
        set => SetValue(IsThinkingProperty, value);
    }

    public string StatusLine
    {
        get => (string)GetValue(StatusLineProperty);
        set => SetValue(StatusLineProperty, value);
    }

    private static void OnAnswerTextChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is MatrixMindCanvas canvas)
        {
            canvas.BeginFormAnswer(e.NewValue as string ?? "");
        }
    }

    private void BeginFormAnswer(string text)
    {
        var clean = (text ?? "").Trim();
        if (string.IsNullOrEmpty(clean))
        {
            _forming = "";
            _particles.Clear();
            _holdingAnswer = false;
            _formProgress = 0;
            return;
        }

        // Ņem pēdējo «Main Brain:» bloku, ja ir sarunas vēsture
        var idx = clean.LastIndexOf("Main Brain:", StringComparison.OrdinalIgnoreCase);
        if (idx >= 0)
        {
            clean = clean[(idx + "Main Brain:".Length)..].Trim();
        }

        if (clean.Length > 900)
        {
            clean = clean[..900] + "…";
        }

        _forming = clean;
        _formProgress = 0;
        _holdingAnswer = false;
        RebuildParticles(clean);
    }

    private void RebuildParticles(string text)
    {
        _particles.Clear();
        if (_size.Width < 40 || _size.Height < 40)
        {
            return;
        }

        const double fontSize = 18;
        const double lineHeight = 24;
        var maxWidth = Math.Min(_size.Width * 0.78, 920);
        var lines = WrapLines(text, maxWidth, fontSize);
        var blockHeight = lines.Count * lineHeight;
        var startY = (_size.Height - blockHeight) / 2.0;
        var dpi = VisualTreeHelper.GetDpi(this).PixelsPerDip;

        for (var li = 0; li < lines.Count; li++)
        {
            var line = lines[li];
            var measured = MeasureLine(line, fontSize, dpi);
            var startX = (_size.Width - measured) / 2.0;
            double x = startX;
            foreach (var ch in line)
            {
                var w = MeasureLine(ch.ToString(), fontSize, dpi);
                if (ch == ' ')
                {
                    x += w;
                    continue;
                }

                _particles.Add(new GlyphParticle
                {
                    TargetChar = ch,
                    TargetX = x,
                    TargetY = startY + li * lineHeight,
                    X = _rng.NextDouble() * _size.Width,
                    Y = _rng.NextDouble() * _size.Height,
                    Vx = (_rng.NextDouble() - 0.5) * 8,
                    Vy = (_rng.NextDouble() - 0.5) * 8,
                    Size = fontSize,
                    Char = Glyphs[_rng.Next(Glyphs.Length)],
                    Settled = false,
                    Delay = _rng.NextDouble() * 0.35,
                });
                x += w;
            }
        }
    }

    private List<string> WrapLines(string text, double maxWidth, double fontSize)
    {
        var dpi = VisualTreeHelper.GetDpi(this).PixelsPerDip;
        var result = new List<string>();
        foreach (var paragraph in text.Replace("\r\n", "\n").Split('\n'))
        {
            if (string.IsNullOrWhiteSpace(paragraph))
            {
                result.Add("");
                continue;
            }

            var words = paragraph.Split(' ');
            var line = "";
            foreach (var word in words)
            {
                var trial = string.IsNullOrEmpty(line) ? word : line + " " + word;
                if (MeasureLine(trial, fontSize, dpi) <= maxWidth || string.IsNullOrEmpty(line))
                {
                    line = trial;
                }
                else
                {
                    result.Add(line);
                    line = word;
                }
            }

            if (!string.IsNullOrEmpty(line))
            {
                result.Add(line);
            }
        }

        if (result.Count > 18)
        {
            result = result.Take(17).ToList();
            result.Add("…");
        }

        return result;
    }

    private double MeasureLine(string s, double fontSize, double dpi)
    {
        var ft = new FormattedText(
            s,
            CultureInfo.InvariantCulture,
            FlowDirection.LeftToRight,
            _typeface,
            fontSize,
            Brushes.White,
            dpi);
        return ft.WidthIncludingTrailingWhitespace;
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

        var cols = Math.Max(28, (int)(_size.Width / 16));
        var drops = new List<Drop>(cols);
        for (var i = 0; i < cols; i++)
        {
            drops.Add(NewDrop(i * 16 + _rng.NextDouble() * 4, spawnTop: true));
        }

        var floaters = new List<Floater>(IsThinking ? 110 : 80);
        for (var i = 0; i < floaters.Capacity; i++)
        {
            floaters.Add(NewFloater());
        }

        _drops.Clear();
        _drops.AddRange(drops);
        _floaters.Clear();
        _floaters.AddRange(floaters);
        _initialized = true;
    }

    private Drop NewDrop(double x, bool spawnTop)
    {
        var len = _rng.Next(10, 26);
        var chars = new char[len];
        for (var i = 0; i < len; i++)
        {
            chars[i] = Glyphs[_rng.Next(Glyphs.Length)];
        }

        return new Drop
        {
            X = x,
            Y = spawnTop ? -_rng.Next(0, (int)_size.Height) : -_rng.Next(40, 400),
            Speed = 3.8 + _rng.NextDouble() * (IsThinking ? 14.0 : 10.0),
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
            Vx = (_rng.NextDouble() - 0.5) * (IsThinking ? 3.2 : 1.6),
            Vy = (_rng.NextDouble() - 0.5) * (IsThinking ? 2.4 : 1.1),
            Char = Glyphs[_rng.Next(Glyphs.Length)],
            Size = 11 + _rng.NextDouble() * 18,
            Alpha = 0.18 + _rng.NextDouble() * 0.55,
            Spin = (_rng.NextDouble() - 0.5) * 0.14,
            Angle = _rng.NextDouble() * Math.PI * 2,
        };
    }

    private void ResetDrop(Drop d)
    {
        var len = _rng.Next(10, 26);
        if (d.Chars.Length != len)
        {
            d.Chars = new char[len];
        }

        for (var i = 0; i < d.Chars.Length; i++)
        {
            d.Chars[i] = Glyphs[_rng.Next(Glyphs.Length)];
        }

        d.Y = -_rng.Next(0, Math.Max(40, (int)_size.Height / 2));
        d.Speed = 3.8 + _rng.NextDouble() * (IsThinking ? 14.0 : 10.0);
        d.Head = 0;
    }

    private void Tick()
    {
        if (!_initialized)
        {
            return;
        }

        _pulse += IsThinking ? 0.12 : 0.04;

        for (var di = 0; di < _drops.Count; di++)
        {
            var d = _drops[di];
            d.Y += d.Speed * (IsThinking ? 1.35 : 1.0);
            d.Head++;
            if (d.Chars.Length > 0 && d.Head % 2 == 0)
            {
                d.Chars[_rng.Next(d.Chars.Length)] = Glyphs[_rng.Next(Glyphs.Length)];
            }

            if (d.Y - d.Chars.Length * 16 > _size.Height)
            {
                ResetDrop(d);
            }
        }

        var cx = _size.Width / 2;
        var cy = _size.Height / 2;
        for (var fi = 0; fi < _floaters.Count; fi++)
        {
            var f = _floaters[fi];
            if (IsThinking && _particles.Count == 0)
            {
                // Domāšanas režīms — hieroglifi velkas pret centru
                f.Vx += (cx - f.X) * 0.0008;
                f.Vy += (cy - f.Y) * 0.0008;
            }

            f.X += f.Vx;
            f.Y += f.Vy;
            f.Angle += f.Spin;
            if (_rng.NextDouble() < 0.04)
            {
                f.Char = Glyphs[_rng.Next(Glyphs.Length)];
            }

            if (f.X < -30 || f.X > _size.Width + 30 || f.Y < -30 || f.Y > _size.Height + 30)
            {
                f.X = _rng.NextDouble() * Math.Max(1, _size.Width);
                f.Y = _rng.NextDouble() * Math.Max(1, _size.Height);
                f.Char = Glyphs[_rng.Next(Glyphs.Length)];
            }
        }

        // Atbildes salidošana
        if (_particles.Count > 0 && !_holdingAnswer)
        {
            _formProgress = Math.Min(1.0, _formProgress + 0.012);
            var settled = 0;
            for (var i = 0; i < _particles.Count; i++)
            {
                var p = _particles[i];
                if (_formProgress < p.Delay)
                {
                    p.Char = Glyphs[_rng.Next(Glyphs.Length)];
                    p.X += p.Vx * 0.3;
                    p.Y += p.Vy * 0.3;
                    continue;
                }

                var t = Math.Min(1.0, (_formProgress - p.Delay) / 0.65);
                // ease-out
                var ease = 1 - Math.Pow(1 - t, 3);
                p.X += (p.TargetX - p.X) * (0.08 + 0.22 * ease);
                p.Y += (p.TargetY - p.Y) * (0.08 + 0.22 * ease);

                var dist = Math.Abs(p.X - p.TargetX) + Math.Abs(p.Y - p.TargetY);
                if (dist < 1.2 || t > 0.92)
                {
                    p.X = p.TargetX;
                    p.Y = p.TargetY;
                    p.Char = p.TargetChar;
                    p.Settled = true;
                    settled++;
                }
                else if (_rng.NextDouble() < 0.35)
                {
                    p.Char = Glyphs[_rng.Next(Glyphs.Length)];
                }
                else if (t > 0.7)
                {
                    p.Char = p.TargetChar;
                }
            }

            if (settled >= _particles.Count * 0.97 || _formProgress >= 0.999)
            {
                foreach (var p in _particles)
                {
                    p.X = p.TargetX;
                    p.Y = p.TargetY;
                    p.Char = p.TargetChar;
                    p.Settled = true;
                }

                _holdingAnswer = true;
            }
        }
        else if (_holdingAnswer)
        {
            // Viegla elpošana uz nokārtotajiem simboliem
            for (var i = 0; i < _particles.Count; i++)
            {
                var p = _particles[i];
                if (_rng.NextDouble() < 0.002)
                {
                    p.Char = Glyphs[_rng.Next(Glyphs.Length)];
                }
                else
                {
                    p.Char = p.TargetChar;
                }
            }
        }
    }

    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc);
        if (_size.Width < 1 || _size.Height < 1 || !_initialized)
        {
            return;
        }

        dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(1, 4, 6)), null, new Rect(_size));

        // Lietus (vājāks, kad atbilde ir salidojusi)
        var rainAlphaScale = _holdingAnswer ? 0.35 : (IsThinking ? 1.15 : 0.85);
        var dropCount = _drops.Count;
        for (var di = 0; di < dropCount; di++)
        {
            if (di >= _drops.Count)
            {
                break;
            }

            var d = _drops[di];
            for (var i = 0; i < d.Chars.Length; i++)
            {
                var y = d.Y - i * 16;
                if (y < -20 || y > _size.Height + 20)
                {
                    continue;
                }

                var t = 1.0 - i / (double)Math.Max(1, d.Chars.Length);
                var g = (byte)(30 + 190 * t * rainAlphaScale);
                var a = (byte)Math.Clamp((int)((i == 0 ? 220 : 40 + 160 * t) * rainAlphaScale), 0, 255);
                var brush = i == 0
                    ? new SolidColorBrush(Color.FromArgb(a, 170, 255, 200))
                    : new SolidColorBrush(Color.FromArgb(a, 0, g, (byte)(g * 0.5)));
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

        // Lidojošie hieroglifi
        if (!_holdingAnswer || IsThinking)
        {
            var floaterCount = _floaters.Count;
            for (var fi = 0; fi < floaterCount; fi++)
            {
                if (fi >= _floaters.Count)
                {
                    break;
                }

                var f = _floaters[fi];
                var alpha = f.Alpha * (_holdingAnswer ? 0.25 : 1.0);
                if (IsThinking)
                {
                    alpha = Math.Min(1, alpha + 0.15 + 0.1 * Math.Sin(_pulse + fi));
                }

                var brush = new SolidColorBrush(Color.FromArgb((byte)(alpha * 255), 0, 255, 140));
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

        // Salidojušie atbildes simboli
        for (var i = 0; i < _particles.Count; i++)
        {
            var p = _particles[i];
            var glow = p.Settled ? (byte)255 : (byte)200;
            var brush = new SolidColorBrush(
                p.Settled
                    ? Color.FromArgb(glow, 140, 255, 190)
                    : Color.FromArgb(210, 0, 255, 120));
            var ft = new FormattedText(
                p.Char.ToString(),
                CultureInfo.InvariantCulture,
                FlowDirection.LeftToRight,
                _typeface,
                p.Size,
                brush,
                VisualTreeHelper.GetDpi(this).PixelsPerDip);
            if (p.Settled)
            {
                // viegls glow
                var glowBrush = new SolidColorBrush(Color.FromArgb(50, 0, 255, 140));
                var glowFt = new FormattedText(
                    p.Char.ToString(),
                    CultureInfo.InvariantCulture,
                    FlowDirection.LeftToRight,
                    _typeface,
                    p.Size + 1.5,
                    glowBrush,
                    VisualTreeHelper.GetDpi(this).PixelsPerDip);
                dc.DrawText(glowFt, new Point(p.X - 0.5, p.Y - 0.5));
            }

            dc.DrawText(ft, new Point(p.X, p.Y));
        }

        // Statuss / «domā…»
        var status = StatusLine;
        if (string.IsNullOrWhiteSpace(status))
        {
            if (IsThinking)
            {
                status = "◈ DOMĀ …";
            }
            else if (_particles.Count == 0 && string.IsNullOrEmpty(_forming))
            {
                status = "◈ MAIN BRAIN · dzīva sistēma";
            }
        }

        if (!string.IsNullOrWhiteSpace(status))
        {
            var sb = new SolidColorBrush(Color.FromArgb(
                (byte)(IsThinking ? 200 + 40 * Math.Sin(_pulse) : 140),
                0, 255, 136));
            var st = new FormattedText(
                status,
                CultureInfo.GetCultureInfo("lv-LV"),
                FlowDirection.LeftToRight,
                _typeface,
                14,
                sb,
                VisualTreeHelper.GetDpi(this).PixelsPerDip);
            dc.DrawText(st, new Point((_size.Width - st.Width) / 2, 28));
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

    private sealed class GlyphParticle
    {
        public double X;
        public double Y;
        public double Vx;
        public double Vy;
        public double TargetX;
        public double TargetY;
        public char Char;
        public char TargetChar;
        public double Size;
        public bool Settled;
        public double Delay;
    }
}
