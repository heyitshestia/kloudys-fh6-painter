using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Animation;

namespace KFPS.Wpf.Theming
{
    public partial class SakuraBackdrop : UserControl
    {
        private Storyboard? _ambientStoryboard;

        public static readonly DependencyProperty IsAmbientMotionEnabledProperty =
            DependencyProperty.Register(
                nameof(IsAmbientMotionEnabled),
                typeof(bool),
                typeof(SakuraBackdrop),
                new PropertyMetadata(true, OnAmbientMotionChanged));

        public bool IsAmbientMotionEnabled
        {
            get => (bool)GetValue(IsAmbientMotionEnabledProperty);
            set => SetValue(IsAmbientMotionEnabledProperty, value);
        }

        public SakuraBackdrop()
        {
            InitializeComponent();
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            UpdateAmbientMotion();
        }

        private void OnUnloaded(object sender, RoutedEventArgs e)
        {
            StopAmbientMotion();
        }

        private static void OnAmbientMotionChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            ((SakuraBackdrop)d).UpdateAmbientMotion();
        }

        private void UpdateAmbientMotion()
        {
            if (!IsLoaded)
                return;

            // Honors the Windows "Show animations in Windows" preference.
            if (!IsAmbientMotionEnabled || !SystemParameters.ClientAreaAnimation)
            {
                StopAmbientMotion();
                return;
            }

            StopAmbientMotion();
            _ambientStoryboard = ((Storyboard)Resources["AmbientMotion"]).Clone();
            _ambientStoryboard.Begin(this, true);
        }

        private void StopAmbientMotion()
        {
            if (_ambientStoryboard == null)
                return;

            _ambientStoryboard.Remove(this);
            _ambientStoryboard = null;
        }
    }
}
