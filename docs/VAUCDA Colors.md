# VAUCDA Color Palette Documentation

---

## Overview

The VAUDA application employs a carefully designed color palette that balances professional medical aesthetics with accessibility and visual hierarchy. The color system is built around trust-inspiring blues, complemented by medical teals and standard status colors for optimal clinical UX.

---

## Primary Color System

### Brand Colors

#### **Primary Blue**
- **Hex:** `#2c5282`
- **RGB:** `rgb(44, 82, 130)`
- **CSS Variable:** `--primary-blue`
- **Usage:** Primary navigation bars, main CTA buttons, headings, primary brand identity
- **Associations:** Trust, professionalism, medical authority

#### **Primary Light Blue**
- **Hex:** `#3182ce`
- **RGB:** `rgb(49, 130, 206)`
- **CSS Variable:** `--primary-light-blue`
- **Usage:** Button hover states, interactive element highlights
- **Associations:** Active interaction states

#### **Secondary Blue**
- **Hex:** `#4299e1`
- **RGB:** `rgb(66, 153, 225)`
- **CSS Variable:** `--secondary-blue`
- **Usage:** Secondary buttons, badges, highlights
- **Associations:** Supporting actions, secondary information

#### **Accent Blue**
- **Hex:** `#63b3ed`
- **RGB:** `rgb(99, 179, 237)`
- **CSS Variable:** `--accent-blue`
- **Usage:** Navigation hover states, links, subtle accents, taglines
- **Associations:** Interactive elements, highlights

---

### Medical Professional Color

#### **Medical Teal**
- **Hex:** `#0d9488`
- **RGB:** `rgb(13, 148, 136)`
- **CSS Variable:** `--medical-teal`
- **Usage:** Medical-specific actions, clinical buttons, healthcare-focused features
- **Hover State:** `#14b8a6`
- **Associations:** Medical procedures, clinical actions, healthcare operations

---

## Functional Status Colors

### Success/Positive States

#### **Success Green**
- **Hex:** `#10b981`
- **RGB:** `rgb(16, 185, 129)`
- **CSS Variable:** `--success-green`
- **Usage:** Success messages, active status indicators, positive confirmations, completed states
- **Light Background:** `#dcfce7` (Success message backgrounds)
- **Lighter Background:** `#ecfdf5` (Card gradient starts)
- **Even Lighter:** `#d1fae5` (Card gradient ends)
- **Dark Text:** `#166534` (Text on light success backgrounds)
- **Medium Green:** `#10b981` (Main success color)
- **Dark Green Titles:** `#065f46` (Dark green headings)
- **Medium Dark Text:** `#047857` (Body text on light backgrounds)
- **Shadow:** `rgba(16, 185, 129, 0.4)` (Glow effects)
- **Associations:** System online, successful operations, connected states

### Warning States

#### **Warning Yellow/Amber**
- **Hex:** `#f59e0b`
- **RGB:** `rgb(245, 158, 11)`
- **CSS Variable:** `--warning-yellow`
- **Usage:** Warning messages, modified/unsaved states, caution indicators
- **Light Background:** `#fef3c7` (Warning message backgrounds)
- **Lightest Background:** `#fefce8` (Card gradient starts)
- **Dark Text:** `#d97706` (Text on light warning backgrounds)
- **Very Dark Text:** `#92400e` (Dark headings on yellow backgrounds)
- **Associations:** Pending actions, modified content, caution

### Error States

#### **Error Red**
- **Hex:** `#ef4444`
- **RGB:** `rgb(239, 68, 68)`
- **CSS Variable:** `--error-red`
- **Usage:** Error messages, failed operations, disconnected states, required field indicators
- **Light Background:** `#fee2e2` (Error message backgrounds)
- **Dark Text:** `#dc2626` (Text on light error backgrounds)
- **Shadow:** `rgba(239, 68, 68, 0.4)` (Glow effects)
- **Associations:** System errors, failed operations, critical alerts

### Informational States

#### **Info Cyan**
- **Hex:** `#06b6d4`
- **RGB:** `rgb(6, 182, 212)`
- **CSS Variable:** `--info-cyan`
- **Usage:** Informational messages, neutral notifications
- **Light Background:** `#dbeafe` (Info message backgrounds)
- **Lighter Background:** `#f0f9ff` (Gradient starts)
- **Medium Light:** `#e0f2fe` (Gradient ends)
- **Border:** `#0ea5e9` (Borders and accents)
- **Dark Text:** `#1d4ed8` (Text on light info backgrounds)
- **Associations:** General information, system messages

---

## Neutral Colors

### Gray Scale

#### **Gray 700 (Custom)**
- **Hex:** `#707783`
- **RGB:** `rgb(112, 119, 131)`
- **CSS Variable:** `--gray-700`
- **Usage:** Secondary text, metadata, status labels

#### **Light Gray Backgrounds**
- `#f9fafb` - Page background, card backgrounds (very common)
- `#f8fafc` - Alternative light background, editor backgrounds
- `#f3f4f6` - Hover states, inactive elements
- `#f7fafc` - Table header backgrounds

#### **Border Grays**
- `#e5e7eb` - Primary border color, dividers, progress bars
- `#e2e8f0` - Secondary borders, section dividers
- `#d1d5db` - Input borders, button outlines
- `#e9ecef` - Alternative border color

#### **Medium Grays**
- `#9ca3af` - Placeholder text, disabled text, secondary labels
- `#6b7280` - Body text (secondary), metadata text, icons
- `#4b5563` - Dark mode borders, dark UI elements
- `#374151` - Primary text color, dark mode backgrounds, section headers

#### **Dark Grays**
- `#2d3748` - Very dark text, headings in reports
- `#1f2937` - Dark headings, titles, dark mode background
- `#718096` - Muted text in reports

#### **Slate Gray**
- `#64748b` - Body text on colored backgrounds

#### **Stone Gray**
- `#78716c` - Alternative body text on warm backgrounds

---

## Specialty Feature Colors

### Purple Accent (Note Generation)
- **Hex:** `#8b5cf6` (Medium Purple)
- **RGB:** `rgb(139, 92, 246)`
- **Usage:** Quick note generation buttons, specialty feature cards
- **Variants:**
  - `#7c3aed` - Purple text on light backgrounds
  - `#6b21a8` - Dark purple for headings and secondary buttons
  - `#f3e8ff` - Light purple for card backgrounds (gradient end)
  - `#faf5ff` - Very light purple for card backgrounds (gradient start)
  - `#dbeafe` - Purple badge backgrounds
  - `#1e40af` - Purple badge text
- **Associations:** Advanced features, document processing, specialty tools

### Template System Colors (from template_manager.css)

#### **Blue System**
- `#3b82f6` - Primary blue for buttons and active states
- `#eff6ff` - Light blue background for active categories
- `#1d4ed8` - Dark blue for active text
- `#2563eb` - Button hover states
- `#60a5fa` - Dark mode focus states

#### **Category Badges**
- `#dbeafe` - Light blue background for specialty badges
- `#1e40af` - Dark blue text for specialty badges
- `#f3e8ff` - Light purple background for type badges
- `#7c3aed` - Purple text for type badges

---

## Interactive Editor Palette (from interactive_editor.css)

### Editor-Specific Colors

#### **Status Indicators**
- **Success/Connected:** `#10b981` (Green with pulse animation)
- **Saving State:** `#f59e0b` (Amber with scale animation)
- **Error State:** `#ef4444` (Red with pulse animation)

#### **Navigation & Progress**
- **Active Section:** `#eff6ff` background with `#3b82f6` left border
- **Complete Status:** `#10b981` (Green checkmark)
- **Incomplete Status:** `#d1d5db` (Light gray)
- **Modified Status:** `#f59e0b` (Amber indicator)

#### **Progress Bar**
- **Background:** `#e5e7eb` (Light gray)
- **Fill:** Linear gradient from `#3b82f6` to `#1d4ed8` (Blue gradient)

#### **Confidence Indicators**
- **Background:** `#e5e7eb` (Light gray)
- **Fill:** Linear gradient from `#ef4444` (red) ? `#f59e0b` (amber) ? `#10b981` (green)

#### **Notifications**
- **Success:** `#10b981` background
- **Error:** `#ef4444` background
- **Warning:** `#f59e0b` background
- **Info:** `#3b82f6` background

#### **Section Highlights**
- **Collaborative Edit:** `#f0fdf4` background with `#10b981` left border
- **Focus/Highlight:** `#3b82f6` with animated box-shadow

---

## Dark Mode Palette

VACA2 includes comprehensive dark mode support with adjusted colors for optimal readability:

### Dark Mode Backgrounds
- **Primary Background:** `#1f2937`
- **Card/Panel Background:** `#374151`
- **Elevated Background:** `#4b5563` (Section headers, footers)

### Dark Mode Borders
- **Primary Border:** `#4b5563`
- **Secondary Border:** `#6b7280`

### Dark Mode Text
- **Primary Text:** `#f9fafb` (Near white)
- **Secondary Text:** `#d1d5db` (Light gray)

### Dark Mode Interactive Elements
- **Buttons:** `#4b5563` background
- **Button Hover:** `#374151` background
- **Primary Button:** `#3b82f6` (Unchanged)
- **Primary Button Hover:** `#2563eb` (Unchanged)
- **Focus Border:** `#60a5fa` (Lighter blue)
- **Focus Shadow:** `rgba(96, 165, 250, 0.1)`

---

## Special Effects & Overlays

### Shadows
- **Light Shadow:** `0 1px 3px rgba(0, 0, 0, 0.1)` - Cards, subtle elevation
- **Medium Shadow:** `0 4px 12px rgba(0, 0, 0, 0.15)` - Hover states, elevated cards
- **Heavy Shadow:** `0 20px 25px rgba(0, 0, 0, 0.15)` - Modals, popups
- **Button Shadows:** Various colored shadows matching button colors with 0.3-0.4 alpha

### Gradients
- **Medical Chat Card:** `linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)` (Light blue)
- **Prompt Settings Card:** `linear-gradient(135deg, #fefce8 0%, #fef3c7 100%)` (Light yellow)
- **Evidence Search Card:** `linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)` (Light green)
- **Note Generation Card:** `linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%)` (Light purple)
- **Progress Bar:** `linear-gradient(90deg, #3b82f6, #1d4ed8)` (Blue gradient)
- **Confidence Bar:** `linear-gradient(90deg, #ef4444, #f59e0b, #10b981)` (Red to green)
- **Validation Report Header:** `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` (Purple gradient)

### Overlay Elements
- **Modal Backdrop:** `rgba(0, 0, 0, 0.5)`
- **Decorative Circles:** 10% opacity of parent color (Various)
- **Status Glows:** `rgba(R, G, B, 0.4)` - Color-matched glows around status indicators

---

## Typography Color Usage

### Primary Headings
- **Main Color:** `var(--primary-blue)` / `#2c5282`
- **Dark Mode:** `#f9fafb`

### Body Text
- **Primary:** `#374151` (Dark gray)
- **Secondary:** `#6b7280` (Medium gray)
- **Tertiary:** `#9ca3af` (Light gray)
- **Dark Mode Primary:** `#f9fafb`
- **Dark Mode Secondary:** `#d1d5db`

### Links & Interactive Text
- **Link Color:** `var(--accent-blue)` / `#63b3ed`
- **Link Hover:** Same as link color
- **Active Link:** `#1d4ed8`

### Placeholder Text
- **Standard:** `#9ca3af`
- **Dark Mode:** `#6b7280`

---

## Loading & Animation Colors

### Loading Spinners
- **Spinner Background:** `#f3f3f3` (Light gray border)
- **Spinner Active:** `var(--primary-blue)` / `#2c5282` (Top border)
- **Dark Mode Spinner:** `#e5e7eb` background with `#3b82f6` active border

### Status Dot Animations
- **Online:** `#10b981` with pulse animation
- **Saving:** `#f59e0b` with scale animation
- **Error:** `#ef4444` with pulse animation

---

## Button Color System

### Primary Button
- **Background:** `var(--primary-blue)` / `#2c5282`
- **Text:** White
- **Hover:** `var(--primary-light-blue)` / `#3182ce`
- **Box Shadow:** `0 4px 12px rgba(59, 130, 246, 0.3)`
- **Hover Shadow:** `0 8px 20px rgba(59, 130, 246, 0.4)`

### Medical Button
- **Background:** `var(--medical-teal)` / `#0d9488`
- **Text:** White
- **Hover:** `#14b8a6`

### Secondary Button
- **Background:** Transparent
- **Border:** `2px solid var(--primary-blue)`
- **Text:** `var(--primary-blue)`
- **Hover Background:** `var(--primary-blue)`
- **Hover Text:** White

### Outline Button
- **Background:** Transparent
- **Border:** `1px solid #d1d5db`
- **Text:** `#374151`
- **Hover Background:** `#f9fafb`
- **Hover Border:** `#9ca3af`

### Icon Button
- **Background:** None
- **Color:** `#6b7280`
- **Hover Background:** `#f3f4f6`
- **Hover Color:** `#374151`

---

## Form Input Colors

### Text Inputs
- **Background:** White / `#1f2937` (dark mode)
- **Border:** `#d1d5db` / `#4b5563` (dark mode)
- **Focus Border:** `var(--primary-blue)` / `#60a5fa` (dark mode)
- **Focus Shadow:** `0 0 0 2px rgba(59, 130, 246, 0.1)` / `rgba(96, 165, 250, 0.1)` (dark mode)
- **Placeholder:** `#9ca3af` / `#6b7280` (dark mode)

### Labels
- **Color:** `#374151`
- **Required Indicator:** `#ef4444` (Red asterisk)

---

## Card & Container Colors

### Standard Card
- **Background:** White / `#374151` (dark mode)
- **Border:** `1px solid #e5e7eb` / `#4b5563` (dark mode)
- **Shadow:** `0 1px 3px rgba(0, 0, 0, 0.1)`
- **Hover Shadow:** `0 4px 12px rgba(0, 0, 0, 0.15)`

### Card Footer
- **Background:** `#fafbfc` / `#4b5563` (dark mode)
- **Border Top:** `1px solid #f3f4f6` / `#4b5563` (dark mode)

### Section Header
- **Background:** `#f9fafb` / `#4b5563` (dark mode)
- **Border:** `2px solid #e5e7eb` (bottom)

---

## Accessibility Considerations

### Color Contrast Ratios

The palette has been designed to meet WCAG AA accessibility standards:

- **Primary Blue on White:** High contrast, AAA compliant
- **Body Text (#374151) on White:** AAA compliant
- **Success Green:** Sufficient contrast for status indicators
- **Error Red:** High contrast for critical messages
- **Links:** Clearly distinguishable from body text

### Color Blindness Support

- Status indicators use both color and iconography
- Critical information is not conveyed through color alone
- Alternative indicators (checkmarks, icons) accompany color states

---

## Usage Guidelines

### When to Use Each Color

1. **Primary Blue (`#2c5282`)**: Main actions, primary navigation, headers
2. **Medical Teal (`#0d9488`)**: Clinical/medical-specific actions
3. **Success Green (`#10b981`)**: Confirmations, successful operations, online status
4. **Warning Yellow (`#f59e0b`)**: Caution, pending actions, unsaved changes
5. **Error Red (`#ef4444`)**: Errors, failures, critical alerts
6. **Info Cyan (`#06b6d4`)**: General information, tips, neutral notices
7. **Purple (`#8b5cf6`)**: Specialty features, advanced functionality

### Consistency Rules

- Always use CSS variables for brand colors when possible
- Maintain hover state brightness increases
- Keep shadow colors matched to their parent elements
- Use gradient backgrounds sparingly for feature differentiation
- Ensure dark mode colors maintain the same semantic meaning

---

## Technical Implementation

### CSS Variables (Defined in :root)

```css
:root {
    --primary-blue: #2c5282;
    --primary-light-blue: #3182ce;
    --secondary-blue: #4299e1;
    --accent-blue: #63b3ed;
    --medical-teal: #0d9488;
    --success-green: #10b981;
    --warning-yellow: #f59e0b;
    --error-red: #ef4444;
    --info-cyan: #06b6d4;
    --gray-700: #707783;
}
```

### Helper Classes

- `.primary-blue` - Background color
- `.text-primary-blue` - Text color
- `.border-primary-blue` - Border color
- `.btn-primary` - Primary button styling
- `.btn-medical` - Medical-specific button styling
- `.status-online` - Success/online color
- `.status-warning` - Warning color
- `.status-error` - Error color
- `.status-info` - Info color

---

## Color Philosophy

The color palette embodies:

1. **Professionalism**: Deep blues convey medical authority and trust
2. **Clarity**: High contrast ratios ensure readability in clinical settings
3. **Safety**: Clear status colors prevent medical errors
4. **Accessibility**: WCAG-compliant colors support all users
5. **Consistency**: Unified palette across all system components
6. **Flexibility**: Dark mode support for extended use scenarios

--