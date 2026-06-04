---
name: Kinetic Dark
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#b9cacb'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#849495'
  outline-variant: '#3b494b'
  surface-tint: '#00dbe9'
  primary: '#dbfcff'
  on-primary: '#00363a'
  primary-container: '#00f0ff'
  on-primary-container: '#006970'
  inverse-primary: '#006970'
  secondary: '#ffb1c3'
  on-secondary: '#66002c'
  secondary-container: '#ff4b89'
  on-secondary-container: '#590026'
  tertiary: '#e5ffba'
  on-tertiary: '#223600'
  tertiary-container: '#a2ef00'
  on-tertiary-container: '#456900'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#7df4ff'
  primary-fixed-dim: '#00dbe9'
  on-primary-fixed: '#002022'
  on-primary-fixed-variant: '#004f54'
  secondary-fixed: '#ffd9e0'
  secondary-fixed-dim: '#ffb1c3'
  on-secondary-fixed: '#3f0019'
  on-secondary-fixed-variant: '#8f0041'
  tertiary-fixed: '#a9f900'
  tertiary-fixed-dim: '#94db00'
  on-tertiary-fixed: '#121f00'
  on-tertiary-fixed-variant: '#334f00'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  display-track:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 24px
    letterSpacing: -0.02em
  headline-deck:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 20px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.03em
  display-track-mobile:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '700'
    lineHeight: 22px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 8px
  margin-mobile: 12px
  margin-desktop: 24px
  touch-target-min: 44px
---

## Brand & Style

The design system is engineered for high-stakes, low-light environments typical of professional DJ booths and mobile performance setups. The brand personality is technical, precise, and high-energy, evoking the feeling of a sophisticated instrument rather than a general-purpose application.

The design style merges **Modern Corporate** precision with **High-Contrast/Bold** functional accents. It utilizes a deep monochromatic base to reduce eye strain, allowing the vibrant waveform data and active states to command immediate attention. Every element is designed with a "performance-first" mindset: high legibility, tactile-responsive aesthetics, and a clinical organization of complex data.

## Colors

The palette is optimized for maximum contrast in dark environments. 

- **Neutral Base:** Uses `#121212` for the foundation and `#1A1A1A` for primary containers to create a subtle sense of depth without relying on heavy shadows.
- **Vibrant Accents:** Neon Blue (`#00F0FF`), Hot Pink (`#FF007A`), and Lime Green (`#ADFF00`) are reserved strictly for data visualization (waveforms, frequency bands) and critical state indicators (active loops, sync).
- **Functional States:** Success/Active states use the Lime Green; Warning/Hot Cues use Hot Pink; System/Information uses Neon Blue.
- **Hierarchy:** Pure white is used sparingly for primary labels to prevent "haloing" against the black background; secondary text uses a muted silver-grey.

## Typography

Typography focuses on immediate scannability. **Inter** is the primary typeface for its exceptional legibility in small sizes and high-density layouts. **JetBrains Mono** is introduced for technical readouts (BPM, Time Remaining, Pitch %) to ensure numerical characters are distinct and do not shift horizontally when values change (tabular figures).

- **Headlines:** Short, punchy, and bold.
- **Technical Labels:** All-caps monospaced text for fixed-width data points.
- **Hierarchy:** Track titles receive the highest weight; artist names and metadata use secondary grey.

## Layout & Spacing

This design system employs a **fluid grid** optimized for high-density information. On mobile, the layout prioritizes the vertical stack of dual waveforms and a condensed library view.

- **Rhythm:** A strict 4px base unit ensures alignment of technical markers like beatgrids and fader increments.
- **Touch Targets:** Despite the high-density requirement, interactive zones (CUE, PLAY, FX toggles) must maintain a minimum 44px hit area.
- **Mobile Reflow:** In portrait mode, decks stack vertically. In landscape, waveforms expand to fill the width while the mixer panel occupies the central 20% of the screen.

## Elevation & Depth

To maintain a "pro-gear" aesthetic, this design system avoids traditional drop shadows. Instead, it uses **Tonal Layers** and **Subtle Outlines**:

- **Layering:** Background is `#121212`. Primary modules (Decks, Mixer) sit on `#1A1A1A`. Floating elements (Modals, FX Popovers) use `#2A2A2A`.
- **Borders:** Elements are separated by 1px solid borders in `#333333` to provide structural definition without visual noise.
- **Glows:** Active states (e.g., an enabled 'Sync' button) utilize a subtle outer glow using the primary accent color (`primary_color_hex` with 20% opacity) to simulate hardware LEDs.

## Shapes

The shape language is **Soft** but disciplined. 

- **Buttons & Containers:** A 0.25rem (4px) radius is applied to maintain a precise, technical look that feels more modern than sharp 90-degree corners but more professional than fully rounded "consumer" UI.
- **Performance Pads:** Square with a 2px radius to maximize surface area for finger strikes.
- **Waveform Containers:** Sharp edges on the internal clipping mask to emphasize the data-driven nature of the visualization.

## Components

- **Buttons:** Use high-contrast fills for primary actions (Play/Pause). Secondary controls (Loop, Slip) use an outlined style that fills with color only when active.
- **Waveforms:** The centerpiece component. Background is black; the "waveform-core" uses the primary color, while "spectral-peaks" use secondary and tertiary colors to denote low/mid/high frequencies.
- **Faders & Knobs:** Linear faders use a high-contrast "cap" with a 1px center line. Rotary knobs are represented as rings that fill clockwise using the accent color.
- **Library Lists:** High-density rows (32px-40px height) with zebra-striping or 1px dividers. The "Currently Playing" track is highlighted with a left-edge accent border in the primary color.
- **Beatgrid Markers:** 1px vertical white lines at 10% opacity, with the "Downbeat" (Beat 1) at 40% opacity for clear rhythmic reference.
- **Status Badges:** Small, all-caps monospaced labels for "MASTER," "SYNC," and "CLIP," using the accent colors to denote status.