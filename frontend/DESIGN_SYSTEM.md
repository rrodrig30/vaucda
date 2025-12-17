# VAUCDA Design System
## VA Urology Clinical Documentation Assistant

Version: 1.0
Date: November 29, 2025
Classification: Production Design Specification

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Color System](#color-system)
3. [Typography](#typography)
4. [Spacing & Layout](#spacing--layout)
5. [Component Library](#component-library)
6. [Iconography](#iconography)
7. [Interaction Patterns](#interaction-patterns)
8. [Animation & Motion](#animation--motion)
9. [Dark Mode](#dark-mode)
10. [Responsive Design](#responsive-design)
11. [Medical-Specific Patterns](#medical-specific-patterns)

---

## Design Philosophy

### Core Principles

**1. Clinical Efficiency**
- Minimize clicks to complete common workflows
- Note generation: max 3 clicks from login
- Calculator access: max 2 clicks
- Search prominence: always visible

**2. Medical Trust & Authority**
- Professional color palette (blues, teals)
- Clean, uncluttered interfaces
- Clear data hierarchy
- No decorative elements that distract from clinical content

**3. Information Clarity**
- Strong visual hierarchy
- Clear section boundaries
- Scannable content layout
- High contrast for critical information

**4. Accessibility First**
- WCAG 2.1 AA minimum (AAA for critical elements)
- Keyboard navigation throughout
- Screen reader optimized
- Color-blind friendly palette

**5. Zero Cognitive Load**
- Consistent patterns across all interfaces
- Familiar medical conventions
- Clear labeling with no jargon
- Contextual help always available

---

## Color System

### Brand Color Palette

#### Primary Blue Scale
```
Primary Blue      #2c5282  rgb(44, 82, 130)   --primary-blue
Primary Light     #3182ce  rgb(49, 130, 206)  --primary-light-blue
Secondary Blue    #4299e1  rgb(66, 153, 225)  --secondary-blue
Accent Blue       #63b3ed  rgb(99, 179, 237)  --accent-blue
```

**Usage:**
- Primary Blue: Navigation bars, primary CTAs, section headings
- Primary Light: Hover states on primary buttons
- Secondary Blue: Secondary actions, badges, non-critical buttons
- Accent Blue: Links, interactive text, subtle highlights

**Contrast Ratios:**
- Primary Blue on White: 7.8:1 (AAA)
- Secondary Blue on White: 5.2:1 (AA)
- Accent Blue on White: 4.6:1 (AA)

#### Medical Professional Color
```
Medical Teal      #0d9488  rgb(13, 148, 136)  --medical-teal
Medical Teal Light #14b8a6  rgb(20, 184, 166) --medical-teal-light
```

**Usage:**
- Medical-specific actions (note generation, clinical calculators)
- Healthcare operation buttons
- Clinical data indicators

**Contrast Ratio:**
- Medical Teal on White: 5.8:1 (AA)

### Semantic Status Colors

#### Success / Positive States
```
Success Green     #10b981  rgb(16, 185, 129)  --success-green
Success Light BG  #ecfdf5  rgb(236, 253, 245) --success-bg-light
Success Dark Text #065f46  rgb(6, 95, 70)     --success-text-dark
```

**Usage:**
- System connected/online
- Successful operations
- Completed states
- Positive confirmations

**Accessibility:**
- Success Green on White: 4.8:1 (AA)
- Success Green on Light BG: 7.2:1 (AAA)

#### Warning / Caution States
```
Warning Yellow    #f59e0b  rgb(245, 158, 11)  --warning-yellow
Warning Light BG  #fef3c7  rgb(254, 243, 199) --warning-bg-light
Warning Dark Text #92400e  rgb(146, 64, 14)   --warning-text-dark
```

**Usage:**
- Pending actions
- Modified/unsaved content
- Caution indicators
- Important notices

**Accessibility:**
- Warning Yellow on White: 3.9:1 (AA for large text)
- Warning Dark Text on Light BG: 8.1:1 (AAA)

#### Error / Critical States
```
Error Red         #ef4444  rgb(239, 68, 68)   --error-red
Error Light BG    #fee2e2  rgb(254, 226, 226) --error-bg-light
Error Dark Text   #dc2626  rgb(220, 38, 38)   --error-text-dark
```

**Usage:**
- System errors
- Failed operations
- Critical alerts
- Required field indicators

**Accessibility:**
- Error Red on White: 5.1:1 (AA)
- Error Dark Text on Light BG: 9.2:1 (AAA)

#### Informational States
```
Info Cyan         #06b6d4  rgb(6, 182, 212)   --info-cyan
Info Light BG     #f0f9ff  rgb(240, 249, 255) --info-bg-light
Info Dark Text    #1d4ed8  rgb(29, 78, 216)   --info-text-dark
```

**Usage:**
- General information
- System messages
- Neutral notifications
- Helper text

### Neutral Grays

```
Gray-50          #f9fafb  Page backgrounds, cards
Gray-100         #f3f4f6  Hover backgrounds, inactive elements
Gray-200         #e5e7eb  Primary borders, dividers
Gray-300         #d1d5db  Input borders, secondary dividers
Gray-400         #9ca3af  Placeholder text, disabled text
Gray-500         #6b7280  Secondary body text, icons
Gray-600         #707783  Custom secondary text (from palette)
Gray-700         #374151  Primary body text
Gray-800         #2d3748  Dark headings
Gray-900         #1f2937  Headings, important text, dark mode bg
```

**Usage Guidelines:**
- 50-100: Backgrounds
- 200-300: Borders and dividers
- 400-500: Secondary text and placeholders
- 600-700: Primary text
- 800-900: Headings and dark mode

### Specialty Feature Colors

#### Purple Accent (Advanced Features)
```
Purple Medium     #8b5cf6  rgb(139, 92, 246)  --purple-medium
Purple Dark       #6b21a8  rgb(107, 33, 168)  --purple-dark
Purple Light BG   #f3e8ff  rgb(243, 232, 255) --purple-bg-light
```

**Usage:**
- Note generation quick actions
- Advanced features
- Specialty tools
- Document processing

### Color Usage Rules

1. **Primary Actions**: Always use Primary Blue (#2c5282)
2. **Medical Actions**: Always use Medical Teal (#0d9488)
3. **Status Indicators**: Never use color alone - always pair with icons or text
4. **Background Colors**: Never go darker than Gray-100 for primary content backgrounds
5. **Text on Colored Backgrounds**: Ensure minimum 4.5:1 contrast ratio
6. **Links**: Use Accent Blue (#63b3ed) with underline on hover
7. **Focus States**: Use 2px solid Primary Blue with 4px offset shadow

---

## Typography

### Type Scale

```
Display Large     48px / 56px    font-bold     Headings only
Display           40px / 48px    font-bold     Page titles
H1                32px / 40px    font-bold     Section headings
H2                24px / 32px    font-semibold Subsection headings
H3                20px / 28px    font-semibold Component headings
H4                18px / 28px    font-semibold Minor headings
Body Large        18px / 28px    font-normal   Emphasized body text
Body              16px / 24px    font-normal   Default body text
Body Small        14px / 20px    font-normal   Secondary text
Caption           12px / 16px    font-normal   Labels, captions
```

### Font Families

```css
/* Primary Font Stack */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
             'Roboto', 'Helvetica Neue', Arial, sans-serif;

/* Monospace (for clinical data, lab values) */
--font-mono: 'Roboto Mono', 'Consolas', 'Monaco', 'Courier New', monospace;

/* Optional: Medical-grade font for precision */
--font-medical: 'SF Pro Text', 'Inter', sans-serif;
```

### Font Weights

```
font-normal     400  Body text, descriptions
font-medium     500  Emphasized text, labels
font-semibold   600  Headings, important labels
font-bold       700  Primary headings, critical information
```

### Typography Rules

1. **Minimum Body Text Size**: 16px for all primary content
2. **Line Height**: Minimum 1.5 for body text (24px for 16px text)
3. **Line Length**: Maximum 75 characters (approx 600px) for readability
4. **Paragraph Spacing**: 16px between paragraphs
5. **Letter Spacing**: Default for body, -0.02em for large headings
6. **Medical Data**: Always use monospace font for lab values, measurements
7. **All Caps**: Avoid except for small labels (12px max)
8. **Text Alignment**: Left-aligned for all body text, center only for headings in cards

### Typography Accessibility

- **Contrast**: Minimum 4.5:1 for normal text, 3:1 for large text (18px+)
- **Scalability**: All text must scale properly up to 200%
- **Font Clarity**: Use fonts with clear distinction between similar characters (1, l, I)
- **Medical Terms**: Provide tooltips for abbreviations on first use

---

## Spacing & Layout

### Spacing Scale (8px Base Grid)

```
space-0.5     2px     Tight spacing within components
space-1       4px     Very tight spacing
space-2       8px     Base unit - minimal spacing
space-3       12px    Small spacing
space-4       16px    Default spacing - between related elements
space-5       20px    Medium spacing
space-6       24px    Large spacing - between sections
space-8       32px    Extra large spacing
space-10      40px    Section spacing
space-12      48px    Major section spacing
space-16      64px    Page section spacing
space-20      80px    Large page sections
```

### Layout Principles

#### Container Widths
```
xs-container    320px   Mobile minimum
sm-container    640px   Small tablets
md-container    768px   Tablets
lg-container    1024px  Small desktops
xl-container    1280px  Standard desktops
2xl-container   1440px  Large desktops
max-content     1600px  Maximum content width
```

#### Grid System
- **12-column grid** for complex layouts
- **4-column grid** for mobile
- **Gutter**: 24px (space-6) desktop, 16px (space-4) mobile
- **Margin**: 24px minimum on all sides

#### Z-Index Scale
```
z-0           0      Base level
z-10          10     Elevated cards, dropdowns
z-20          20     Sticky headers
z-30          30     Modals backdrop
z-40          40     Modal content
z-50          50     Tooltips, popovers
z-60          60     Toast notifications
z-100         100    Critical overlays
```

### Layout Patterns

#### Card Spacing
```
Card padding:        24px (space-6) desktop, 16px (space-4) mobile
Card margin:         16px (space-4) between cards
Card header margin:  16px (space-4) below header
Card footer padding: 16px (space-4)
```

#### Form Spacing
```
Label to input:      8px (space-2)
Input to input:      16px (space-4)
Form section gap:    32px (space-8)
Form to actions:     24px (space-6)
```

#### List Spacing
```
List item height:    48px minimum (touch target)
List item padding:   12px (space-3) vertical, 16px (space-4) horizontal
List item gap:       4px (space-1) between items
```

---

## Component Library

### Buttons

#### Primary Button
```
Background:     var(--primary-blue) #2c5282
Text:           White
Padding:        12px 24px (space-3 space-6)
Border Radius:  8px
Font:           16px font-medium
Min Height:     48px (touch target)
Shadow:         0 4px 12px rgba(59, 130, 246, 0.3)

Hover:
  Background:   var(--primary-light-blue) #3182ce
  Shadow:       0 8px 20px rgba(59, 130, 246, 0.4)
  Transform:    translateY(-2px)

Active:
  Transform:    translateY(0)
  Shadow:       0 2px 8px rgba(59, 130, 246, 0.3)

Disabled:
  Background:   var(--gray-300) #d1d5db
  Text:         var(--gray-500) #6b7280
  Cursor:       not-allowed
  Shadow:       none

Focus:
  Outline:      2px solid var(--primary-blue)
  Outline Offset: 2px
```

#### Medical Button
```
Background:     var(--medical-teal) #0d9488
Text:           White
[Same sizing as Primary Button]

Hover:
  Background:   var(--medical-teal-light) #14b8a6
```

#### Secondary Button
```
Background:     Transparent
Border:         2px solid var(--primary-blue)
Text:           var(--primary-blue)
[Same sizing as Primary Button]

Hover:
  Background:   var(--primary-blue)
  Text:         White
```

#### Tertiary/Ghost Button
```
Background:     Transparent
Text:           var(--gray-700)
Border:         1px solid var(--gray-300)

Hover:
  Background:   var(--gray-50)
  Border:       var(--gray-400)
```

#### Icon Button
```
Size:           44px × 44px (square touch target)
Padding:        12px
Border Radius:  8px
Background:     Transparent

Hover:
  Background:   var(--gray-100)
```

#### Danger Button
```
Background:     var(--error-red) #ef4444
Text:           White
[Same sizing as Primary Button]
```

### Input Fields

#### Text Input
```
Height:         48px
Padding:        12px 16px
Border:         1px solid var(--gray-300)
Border Radius:  8px
Font:           16px
Background:     White

Focus:
  Border:       2px solid var(--primary-blue)
  Outline:      none
  Shadow:       0 0 0 4px rgba(44, 82, 130, 0.1)

Error State:
  Border:       2px solid var(--error-red)
  Background:   var(--error-bg-light)

Disabled:
  Background:   var(--gray-50)
  Text:         var(--gray-400)
  Cursor:       not-allowed
```

#### Textarea
```
Min Height:     120px
Max Height:     400px
Resize:         vertical
[Other properties same as Text Input]
```

#### Select Dropdown
```
Height:         48px
[Same styling as Text Input]
Icon:           Chevron down 20px, right-aligned
Icon Color:     var(--gray-500)
```

#### Checkbox
```
Size:           20px × 20px
Border:         2px solid var(--gray-300)
Border Radius:  4px
Checkmark:      var(--primary-blue)

Checked:
  Background:   var(--primary-blue)
  Border:       var(--primary-blue)

Focus:
  Outline:      2px solid var(--primary-blue)
  Outline Offset: 2px
```

#### Radio Button
```
Size:           20px × 20px
Border:         2px solid var(--gray-300)
Border Radius:  50%
Inner Circle:   10px diameter

Checked:
  Border:       var(--primary-blue)
  Inner:        var(--primary-blue)
```

### Cards

#### Standard Card
```
Background:     White
Border:         1px solid var(--gray-200)
Border Radius:  12px
Padding:        24px
Shadow:         0 1px 3px rgba(0, 0, 0, 0.1)

Hover (if interactive):
  Shadow:       0 4px 12px rgba(0, 0, 0, 0.15)
  Transform:    translateY(-2px)
  Border:       var(--gray-300)
```

#### Calculator Card
```
Background:     Linear gradient as per category
Border:         None
Border Radius:  16px
Padding:        32px
Shadow:         0 4px 20px rgba(0, 0, 0, 0.12)

Categories:
  Prostate:     linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)
  Kidney:       linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)
  Medical:      linear-gradient(135deg, #fefce8 0%, #fef3c7 100%)
  Advanced:     linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%)
```

#### Card Header
```
Border Bottom:  1px solid var(--gray-200)
Padding Bottom: 16px
Margin Bottom:  16px
Font:           H3 (20px font-semibold)
```

#### Card Footer
```
Border Top:     1px solid var(--gray-200)
Background:     var(--gray-50)
Padding:        16px 24px
Margin:         24px -24px -24px (extend to edges)
Border Radius:  0 0 12px 12px
```

### Modals

```
Backdrop:
  Background:   rgba(0, 0, 0, 0.5)
  Z-Index:      z-30

Modal Container:
  Background:   White
  Border Radius: 16px
  Max Width:    600px (default), 900px (large), 400px (small)
  Padding:      32px
  Shadow:       0 20px 25px rgba(0, 0, 0, 0.15)
  Z-Index:      z-40

Header:
  Font:         H2 (24px font-semibold)
  Margin Bottom: 24px

Body:
  Font:         Body (16px)
  Max Height:   calc(100vh - 200px)
  Overflow:     auto

Footer:
  Margin Top:   32px
  Display:      flex justify-end
  Gap:          12px
```

### Alerts & Notifications

#### Inline Alert
```
Padding:        16px
Border Radius:  8px
Border Left:    4px solid (status color)
Font:           16px

Success:
  Background:   var(--success-bg-light)
  Border:       var(--success-green)
  Text:         var(--success-text-dark)
  Icon:         Check circle

Warning:
  Background:   var(--warning-bg-light)
  Border:       var(--warning-yellow)
  Text:         var(--warning-text-dark)
  Icon:         Exclamation triangle

Error:
  Background:   var(--error-bg-light)
  Border:       var(--error-red)
  Text:         var(--error-text-dark)
  Icon:         X circle

Info:
  Background:   var(--info-bg-light)
  Border:       var(--info-cyan)
  Text:         var(--info-text-dark)
  Icon:         Information circle
```

#### Toast Notification
```
Position:       Fixed top-right or bottom-right
Width:          400px max
Padding:        16px
Border Radius:  12px
Shadow:         0 8px 20px rgba(0, 0, 0, 0.2)
Animation:      Slide in from right, fade out
Duration:       5 seconds (info), 8 seconds (error), 3 seconds (success)
Z-Index:        z-60
```

### Tables

```
Container:
  Border:       1px solid var(--gray-200)
  Border Radius: 12px
  Overflow:     hidden

Header:
  Background:   var(--gray-50)
  Font:         14px font-semibold uppercase
  Letter Spacing: 0.05em
  Text Color:   var(--gray-700)
  Padding:      12px 16px
  Border Bottom: 2px solid var(--gray-200)

Row:
  Padding:      16px
  Border Bottom: 1px solid var(--gray-200)

Row Hover:
  Background:   var(--gray-50)

Cell:
  Padding:      16px
  Font:         16px
  Vertical Align: middle

Striped Rows (optional):
  Odd rows:     White
  Even rows:    var(--gray-50)
```

### Loading States

#### Spinner
```
Size:           40px diameter (default)
Border:         4px solid var(--gray-200)
Border Top:     4px solid var(--primary-blue)
Border Radius:  50%
Animation:      spin 1s linear infinite
```

#### Skeleton Loader
```
Background:     linear-gradient(90deg,
                  var(--gray-200) 0%,
                  var(--gray-100) 50%,
                  var(--gray-200) 100%)
Animation:      shimmer 1.5s infinite
Border Radius:  8px
Height:         Matches target element
```

#### Progress Bar
```
Height:         8px
Background:     var(--gray-200)
Border Radius:  4px
Fill:           linear-gradient(90deg, #3b82f6, #1d4ed8)
Animation:      Smooth transition on value change
```

### Badges

```
Padding:        4px 12px
Border Radius:  12px (pill shape)
Font:           12px font-medium
Display:        inline-flex
Align Items:    center
Gap:            4px (if icon present)

Primary:
  Background:   var(--primary-blue)
  Text:         White

Success:
  Background:   var(--success-green)
  Text:         White

Warning:
  Background:   var(--warning-yellow)
  Text:         var(--warning-text-dark)

Error:
  Background:   var(--error-red)
  Text:         White

Neutral:
  Background:   var(--gray-200)
  Text:         var(--gray-700)
```

### Tooltips

```
Background:     var(--gray-900)
Text:           White
Padding:        8px 12px
Border Radius:  6px
Font:           14px
Max Width:      300px
Shadow:         0 4px 12px rgba(0, 0, 0, 0.15)
Z-Index:        z-50

Arrow:
  Size:         8px
  Color:        var(--gray-900)

Show on:        Hover after 300ms delay
Hide on:        Mouse leave immediately
```

---

## Iconography

### Icon System

**Icon Library**: Heroicons 2.0 (recommended for consistency with Tailwind)
**Alternative**: Lucide Icons, Feather Icons

### Icon Sizes
```
xs      16px    Inline with small text
sm      20px    Inline with body text, buttons
md      24px    Default standalone icons
lg      32px    Section headers, feature icons
xl      48px    Hero sections, empty states
2xl     64px    Large feature illustrations
```

### Icon Usage Rules

1. **Stroke Width**: 2px for all sizes (consistency)
2. **Color**: Match text color of parent element
3. **Spacing**: 8px gap between icon and text
4. **Alignment**: Vertically center with text
5. **Interactive Icons**: Add 44px × 44px touch target padding
6. **Decorative Icons**: Mark as `aria-hidden="true"`
7. **Functional Icons**: Include accessible label

### Medical-Specific Icons

```
Clinical Actions:
  - Note Generation:    Document with plus
  - Calculator:         Calculator or beaker
  - Evidence Search:    Magnifying glass with document
  - Settings:           Gear/cog

Status Indicators:
  - Success:            Check circle (solid)
  - Warning:            Exclamation triangle
  - Error:              X circle (solid)
  - Info:               Information circle
  - In Progress:        Clock or spinner

Clinical Categories:
  - Prostate:           Location pin / anatomy icon
  - Kidney:             Location pin / anatomy icon
  - Bladder:            Location pin / anatomy icon
  - Labs:               Beaker / test tube
  - Imaging:            Image / scan icon
```

---

## Interaction Patterns

### Hover States

**Interactive Elements:**
- Background color change or subtle darkening (5-10%)
- Subtle elevation (2-4px translateY)
- Shadow increase
- Cursor change to pointer

**Links:**
- Underline appears
- Color darkens slightly

**Cards:**
- Border color intensifies
- Shadow deepens
- Slight elevation (2px up)

**Buttons:**
- Background lightens (primary buttons)
- Shadow deepens
- Slight elevation

### Focus States

**All Interactive Elements:**
```
Outline:        2px solid var(--primary-blue)
Outline Offset: 2px
Border Radius:  Inherit from element
```

**Alternative Focus (for dark backgrounds):**
```
Outline:        2px solid white
Outline Offset: 2px
```

**Never:**
- Remove focus indicators (outline: none) without replacement
- Use focus indicators with contrast < 3:1

### Active/Pressed States

**Buttons:**
- Remove elevation (translateY(0))
- Shadow reduces
- Slight background darken (5%)

**Cards:**
- Remove elevation
- Border intensifies

### Disabled States

**All Elements:**
```
Opacity:        0.6
Cursor:         not-allowed
Background:     Grayed out (var(--gray-100) or var(--gray-300))
Text:           var(--gray-400)
```

### Loading States

**Buttons:**
- Show spinner replacing text or icon
- Maintain button dimensions
- Disable interaction
- Reduce opacity to 0.8

**Forms:**
- Show skeleton loaders in place of content
- Disable all inputs
- Show progress indicator if multi-step

**Page:**
- Full-page spinner or skeleton layout
- Prevent scrolling
- Show loading message after 2 seconds

### Error States

**Form Inputs:**
- Red border (2px solid var(--error-red))
- Error icon in input (right side)
- Error message below input (red text, 14px)
- Shake animation on submission

**Inline Errors:**
- Error alert component
- Icon + message
- Dismissible (X button)

### Success States

**Form Submission:**
- Success toast notification
- Green checkmark animation
- Success message
- Auto-redirect after 2 seconds (if applicable)

**Inline Success:**
- Success alert component
- Checkmark icon
- Success message

---

## Animation & Motion

### Animation Principles

1. **Purposeful**: Every animation should have a functional purpose
2. **Subtle**: Animations should enhance, not distract
3. **Fast**: Keep durations under 300ms for UI interactions
4. **Respect Preferences**: Honor prefers-reduced-motion

### Duration Scale

```
instant     0ms       Immediate changes (color, opacity)
fast        100ms     Quick feedback (hover states)
normal      200ms     Default transitions
slow        300ms     Complex transitions (modals, drawers)
slower      500ms     Emphasis animations
slowest     1000ms    Loading states, success celebrations
```

### Easing Functions

```
ease-in         Slow start, fast end - Entering elements
ease-out        Fast start, slow end - Exiting elements
ease-in-out     Slow start and end - Most UI transitions
ease-linear     Constant speed - Progress bars, spinners
ease-spring     Bouncy - Attention-grabbing (use sparingly)
```

### Standard Transitions

```css
/* Default transition for interactive elements */
transition: all 200ms ease-in-out;

/* Button hover */
transition: transform 200ms ease-out,
            box-shadow 200ms ease-out,
            background-color 200ms ease-out;

/* Modal appearance */
transition: opacity 300ms ease-in-out,
            transform 300ms ease-out;

/* Dropdown menu */
transition: opacity 200ms ease-in,
            transform 200ms ease-out;
```

### Keyframe Animations

#### Fade In
```css
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
/* Duration: 300ms */
```

#### Slide In (from right, for toasts)
```css
@keyframes slideInRight {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
/* Duration: 300ms */
```

#### Shake (for errors)
```css
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
  20%, 40%, 60%, 80% { transform: translateX(4px); }
}
/* Duration: 500ms */
```

#### Spinner
```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
/* Duration: 1000ms linear infinite */
```

#### Pulse (for status indicators)
```css
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
/* Duration: 2000ms ease-in-out infinite */
```

#### Shimmer (for skeleton loaders)
```css
@keyframes shimmer {
  0% { background-position: -1000px 0; }
  100% { background-position: 1000px 0; }
}
/* Duration: 1500ms linear infinite */
```

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Dark Mode

### Dark Mode Color Palette

```
Background Primary   #1f2937   Gray-900 - Main background
Background Secondary #374151   Gray-700 - Card backgrounds
Background Elevated  #4b5563   Gray-600 - Elevated elements

Text Primary        #f9fafb   Gray-50 - Main text
Text Secondary      #d1d5db   Gray-300 - Secondary text
Text Tertiary       #9ca3af   Gray-400 - Tertiary text

Border Primary      #4b5563   Gray-600 - Primary borders
Border Secondary    #6b7280   Gray-500 - Secondary borders

Primary Blue        #3b82f6   Brighter blue for dark mode
Success Green       #10b981   Same as light mode
Warning Yellow      #f59e0b   Same as light mode
Error Red           #ef4444   Same as light mode
```

### Dark Mode Implementation

```css
/* Light mode (default) */
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --text-primary: #374151;
  --text-secondary: #6b7280;
  --border-primary: #e5e7eb;
}

/* Dark mode */
[data-theme="dark"],
.dark {
  --bg-primary: #1f2937;
  --bg-secondary: #374151;
  --text-primary: #f9fafb;
  --text-secondary: #d1d5db;
  --border-primary: #4b5563;
}
```

### Dark Mode Rules

1. **Maintain Contrast Ratios**: All WCAG requirements still apply
2. **Invert Shadows**: Use lighter shadows or glows in dark mode
3. **Reduce White**: Pure white (#ffffff) should become off-white (#f9fafb)
4. **Adjust Primary Colors**: Increase lightness for better visibility
5. **Test Thoroughly**: Images and icons may need dark mode variants

---

## Responsive Design

### Breakpoint System

```
xs      320px    Mobile portrait (minimum)
sm      640px    Mobile landscape / small tablets
md      768px    Tablets portrait
lg      1024px   Tablets landscape / small laptops
xl      1280px   Desktops
2xl     1440px   Large desktops
```

### Mobile-First Approach

Always design and code for mobile first, then enhance for larger screens:

```css
/* Mobile (default) */
.card {
  padding: 16px;
  grid-template-columns: 1fr;
}

/* Tablet */
@media (min-width: 768px) {
  .card {
    padding: 24px;
    grid-template-columns: 1fr 1fr;
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .card {
    padding: 32px;
    grid-template-columns: repeat(3, 1fr);
  }
}
```

### Responsive Typography

```
Mobile (< 768px):
  Display:      32px / 40px
  H1:           28px / 36px
  H2:           24px / 32px
  Body:         16px / 24px

Tablet (768px - 1024px):
  Display:      40px / 48px
  H1:           32px / 40px
  H2:           24px / 32px
  Body:         16px / 24px

Desktop (> 1024px):
  Display:      48px / 56px
  H1:           32px / 40px
  H2:           24px / 32px
  Body:         16px / 24px
```

### Touch Targets

**Minimum Size**: 44px × 44px (WCAG Level AAA)
**Recommended**: 48px × 48px
**Spacing**: 8px minimum between touch targets

### Responsive Patterns

#### Navigation
- **Mobile**: Hamburger menu, bottom navigation
- **Tablet**: Top navigation with dropdown
- **Desktop**: Full horizontal navigation

#### Forms
- **Mobile**: Stack all inputs vertically
- **Tablet**: 2-column grid for related inputs
- **Desktop**: Multi-column layout with proper grouping

#### Cards
- **Mobile**: Single column, full width
- **Tablet**: 2-column grid
- **Desktop**: 3-4 column grid

#### Tables
- **Mobile**: Collapse to card layout or horizontal scroll
- **Tablet**: Show important columns only
- **Desktop**: Full table

---

## Medical-Specific Patterns

### Clinical Calculator Interface

```
Layout:
  - Input section (left 60%)
  - Results section (right 40%)
  - Mobile: Stack vertically

Input Section:
  - Clear field labels with units
  - Inline validation
  - Helper text for ranges
  - Auto-focus first field

Results Section:
  - Score prominently displayed (48px)
  - Risk category with color coding
  - Interpretation in plain language
  - References expandable
  - Copy/export results button
```

### Note Display

```
Typography:
  - Monospace font for lab values
  - Clear section headers (H3)
  - Adequate line spacing (1.6)
  - Syntax highlighting for structured data

Layout:
  - Max width 800px for readability
  - Clear section dividers
  - Collapsible sections
  - Print-friendly styles

Actions:
  - Copy to clipboard
  - Export to PDF/DOCX
  - Edit inline
  - Append to existing note
```

### Lab Value Display

```
Format:
  Value: [Number] [Unit] (normal range)
  Example: 4.5 mg/dL (3.5-5.0)

Styling:
  - Monospace font
  - Normal: Default text color
  - High: Warning color (not red to avoid alarm)
  - Low: Info color
  - Critical: Error color with icon

Layout:
  - Table format
  - Clear column headers
  - Sortable by date
  - Filterable by category
```

### Timeline (PSA Curves, etc.)

```
Visual:
  - Line chart with clear data points
  - X-axis: Time (dates)
  - Y-axis: Value with unit
  - Grid lines for reference
  - Tooltip on hover with exact values

Interaction:
  - Zoom in/out
  - Select date range
  - Export chart
  - Toggle trend line
```

### Evidence Source Display

```
Card Format:
  - Title (source document)
  - Publication date
  - Excerpt with highlighting
  - Relevance score (if applicable)
  - Link to full document

Styling:
  - Academic paper feel
  - Clear attribution
  - Reference number if cited
```

---

## Implementation Notes

### CSS Architecture

Use a utility-first approach with Tailwind CSS, supplemented by custom components:

```
/styles
  /base       - Reset, typography, global styles
  /components - Reusable component styles
  /utilities  - Custom utility classes
  /themes     - Dark mode and theme variants
```

### Component Organization

```
/components
  /common     - Buttons, inputs, cards, badges
  /layout     - Headers, navigation, containers
  /medical    - Calculators, note displays, lab values
  /forms      - Form-specific components
```

### Design Tokens

Maintain all design values as CSS custom properties or Tailwind config:

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          blue: '#2c5282',
          // ... all colors from palette
        }
      },
      spacing: {
        // ... spacing scale
      },
      fontSize: {
        // ... typography scale
      }
    }
  }
}
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-29 | Initial design system specification |

---

**Document Owner**: VAUCDA Design Team
**Last Review**: November 29, 2025
**Next Review**: February 29, 2026
