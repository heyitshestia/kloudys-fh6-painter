using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Animation;

namespace KFPS.Wpf.Theming
{
    public partial class NightBlossomBackdrop : UserControl
    {
        public static readonly DependencyProperty IsAmbientMotionEnabledProperty =
            DependencyProperty.Register(
                "IsAmbientMotionEnabled",
                typeof(bool),
                typeof(NightBlossomBackdrop),
                new PropertyMetadata(true, OnAmbientMotionChanged));

        private Storyboard? _ambientMotion;
        private bool _storyboardStarted;

        public NightBlossomBackdrop()
        {
            InitializeComponent();
        }

        public bool IsAmbientMotionEnabled
        {
            get { return (bool)GetValue(IsAmbientMotionEnabledProperty); }
            set { SetValue(IsAmbientMotionEnabledProperty, value); }
        }

        private static void OnAmbientMotionChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is NightBlossomBackdrop backdrop && backdrop.IsLoaded)
            {
                backdrop.ApplyMotionState();
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            if (_ambientMotion == null)
            {
                _ambientMotion = (Storyboard)Resources["AmbientMotion"];
            }

            ApplyMotionState();
        }

        private void OnUnloaded(object sender, RoutedEventArgs e)
        {
            if (_storyboardStarted && _ambientMotion != null)
            {
                _ambientMotion.Remove(this);
                _storyboardStarted = false;
            }
        }

        private void ApplyMotionState()
        {
            if (_ambientMotion == null)
            {
                return;
            }

            bool shouldAnimate = IsAmbientMotionEnabled && SystemParameters.ClientAreaAnimation;

            if (shouldAnimate)
            {
                if (!_storyboardStarted)
                {
                    _ambientMotion.Begin(this, HandoffBehavior.SnapshotAndReplace, true);
                    _storyboardStarted = true;
                }
                else
                {
                    _ambientMotion.Resume(this);
                }
            }
            else if (_storyboardStarted)
            {
                _ambientMotion.Pause(this);
            }
        }
    }
}
