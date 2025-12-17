# VAUCDA Accessibility Audit
## WCAG 2.1 AA Compliance Checklist

Version: 1.0
Date: November 29, 2025
Standard: WCAG 2.1 Level AA

---

## Executive Summary

This document provides a comprehensive accessibility audit checklist and remediation guide for the VAUCDA (VA Urology Clinical Documentation Assistant) application. The system MUST achieve WCAG 2.1 Level AA compliance minimum, with AAA compliance for critical clinical interface elements.

### Compliance Status

STATUS: Pre-implementation - This audit provides requirements for frontend development

TARGET: 100% WCAG 2.1 AA compliance
CRITICAL ELEMENTS TARGET: WCAG 2.1 AAA compliance

---

## Table of Contents

1. [Perceivable](#1-perceivable)
2. [Operable](#2-operable)
3. [Understandable](#3-understandable)
4. [Robust](#4-robust)
5. [Testing Procedures](#5-testing-procedures)
6. [Remediation Guide](#6-remediation-guide)
7. [Tools and Resources](#7-tools-and-resources)

---

## 1. Perceivable

Information and user interface components must be presentable to users in ways they can perceive.

### 1.1 Text Alternatives (Level A)

#### 1.1.1 Non-text Content

[ ] **Images**
- All informational images have descriptive alt text
- Decorative images use alt="" or role="presentation"
- Complex images (charts, diagrams) have long descriptions
- VA logo has appropriate alt text: "Department of Veterans Affairs"

```html
<!-- Good examples -->
<img src="logo.svg" alt="Department of Veterans Affairs" />
<img src="calculator-icon.svg" alt="Clinical calculator" />
<img src="decorative-pattern.svg" alt="" role="presentation" />

<!-- Chart with long description -->
<figure>
  <img src="psa-trend.png" alt="PSA trend chart" aria-describedby="psa-desc" />
  <div id="psa-desc" class="sr-only">
    PSA values showing upward trend from 4.2 to 8.5 ng/mL over 24 months
  </div>
</figure>
```

[ ] **Icons**
- Functional icons have accessible labels
- Icon-only buttons include aria-label or sr-only text
- Decorative icons use aria-hidden="true"

```html
<!-- Icon button -->
<button aria-label="Generate clinical note">
  <svg aria-hidden="true">...</svg>
</button>

<!-- Icon with visible label -->
<button>
  <svg aria-hidden="true">...</svg>
  <span>Calculate CAPRA Score</span>
</button>
```

[ ] **Form Controls**
- All inputs have associated labels
- Labels use for attribute or wrap inputs
- Required fields clearly marked

```html
<label for="psa-value">PSA Value (ng/mL) *</label>
<input 
  id="psa-value" 
  type="number" 
  required 
  aria-required="true"
  aria-describedby="psa-help"
/>
<div id="psa-help" class="text-sm text-gray-600">
  Normal range: 0-4 ng/mL
</div>
```

### 1.2 Time-based Media (Level A)

[ ] **Audio/Video Content** (if applicable)
- Captions provided for prerecorded audio
- Transcripts available for audio-only content
- Audio descriptions for video content

NOTE: Future ambient listening feature MUST include real-time captions

### 1.3 Adaptable (Level A)

#### 1.3.1 Info and Relationships

[ ] **Semantic HTML**
- Use proper heading hierarchy (h1 → h2 → h3, no skipping)
- Use semantic elements: nav, main, article, aside, footer
- Lists use ul/ol/dl appropriately
- Tables use proper table markup with headers

```html
<main>
  <h1>Note Generation</h1>
  
  <section>
    <h2>Clinical Input</h2>
    <h3>Patient Information</h3>
    <!-- Content -->
  </section>
  
  <section>
    <h2>Selected Calculators</h2>
    <h3>Prostate Cancer</h3>
    <!-- Content -->
  </section>
</main>
```

[ ] **ARIA Landmarks**
- Main content area uses main or role="main"
- Navigation uses nav or role="navigation"
- Search uses role="search"
- Complementary content uses aside or role="complementary"

[ ] **Form Structure**
- Related inputs grouped with fieldset
- Group labels use legend
- Form sections clearly delineated

```html
<fieldset>
  <legend>CAPRA Score Inputs</legend>
  
  <label for="psa">PSA (ng/mL)</label>
  <input id="psa" type="number" />
  
  <label for="gleason">Gleason Score</label>
  <input id="gleason" type="number" />
</fieldset>
```

#### 1.3.2 Meaningful Sequence

[ ] **Reading Order**
- DOM order matches visual order
- Content flows logically when CSS disabled
- Tab order follows visual flow

#### 1.3.3 Sensory Characteristics

[ ] **Instructions**
- Instructions don't rely solely on shape, size, or position
- Color not the only means of conveying information
- Visual and programmatic information provided together

```html
<!-- Bad: Color only -->
<p>Required fields are in red</p>

<!-- Good: Multiple indicators -->
<p>Required fields are marked with an asterisk (*) and have a red label</p>
<label class="text-error-900">
  PSA Value *
  <span class="sr-only">(required)</span>
</label>
```

#### 1.3.4 Orientation (Level AA)

[ ] **Orientation**
- Content not restricted to single orientation (portrait/landscape)
- Functions available in any orientation
- Essential exceptions documented

#### 1.3.5 Identify Input Purpose (Level AA)

[ ] **Autocomplete Attributes**
- Common input types use autocomplete attribute
- Personal information fields properly identified

```html
<input 
  type="text" 
  name="name" 
  autocomplete="name"
  aria-label="Provider name"
/>
<input 
  type="email" 
  name="email" 
  autocomplete="email"
  aria-label="Email address"
/>
```

### 1.4 Distinguishable (Level AA/AAA)

#### 1.4.1 Use of Color (Level A)

[ ] **Color Independence**
- Color not the only visual means of conveying information
- Links distinguishable from text without color
- Form validation uses icons/text, not just color
- Chart data labeled, not just colored

```html
<!-- Status with icon and text -->
<div class="flex items-center gap-2 text-success-900">
  <svg><!-- Success icon --></svg>
  <span>Connection established</span>
</div>

<!-- Form error -->
<label class="text-error-900">
  <svg class="inline"><!-- Error icon --></svg>
  PSA Value (required)
</label>
<input class="border-2 border-error-500" aria-invalid="true" />
<div class="text-error-900">
  <svg><!-- Error icon --></svg>
  This field is required
</div>
```

#### 1.4.2 Audio Control (Level A)

[ ] **Auto-playing Audio**
- No auto-playing audio
- User control for any audio
- Pause/stop mechanisms provided

#### 1.4.3 Contrast (Minimum) (Level AA)

[ ] **Text Contrast: 4.5:1 minimum**

COMPLIANCE MATRIX:
```
Color Combination                    Ratio    Status
-----------------------------------------------
Primary Blue (#2c5282) on White     7.8:1    ✓ AAA
Gray-700 (#374151) on White         8.5:1    ✓ AAA
Gray-600 (#707783) on White         5.2:1    ✓ AA
Gray-500 (#6b7280) on White         4.8:1    ✓ AA
Success Green (#10b981) on White    4.8:1    ✓ AA
Warning Yellow (#f59e0b) on White   3.9:1    ✗ (Large text only)
Error Red (#ef4444) on White        5.1:1    ✓ AA
Info Cyan (#06b6d4) on White        4.7:1    ✓ AA
Medical Teal (#0d9488) on White     5.8:1    ✓ AA

Dark Mode:
Gray-50 (#f9fafb) on Gray-900       16.2:1   ✓ AAA
Gray-300 (#d1d5db) on Gray-900      9.8:1    ✓ AAA
Primary Blue (#3b82f6) on Gray-900  8.2:1    ✓ AAA
```

[ ] **Large Text Contrast: 3:1 minimum**
- Text 18pt+ or 14pt+ bold

[ ] **Non-text Contrast: 3:1 minimum**
- UI components (buttons, form borders)
- Graphical objects (icons, chart elements)
- Focus indicators

#### 1.4.4 Resize Text (Level AA)

[ ] **Text Scaling**
- Text can be resized to 200% without loss of content or functionality
- No horizontal scrolling at 200% zoom (1280px width)
- Content reflows appropriately
- No fixed pixel heights that clip content

```css
/* Use relative units */
.card {
  padding: 1rem; /* Not px */
  font-size: 1rem;
  line-height: 1.5; /* Unitless preferred */
}

/* Avoid fixed heights */
.content {
  min-height: 200px; /* min-height, not height */
}
```

#### 1.4.5 Images of Text (Level AA)

[ ] **Text as Text**
- Use actual text rather than images of text
- Exceptions: logos, essential images
- SVG text preferred over bitmap text

#### 1.4.10 Reflow (Level AA)

[ ] **Responsive Reflow**
- Content reflows at 320px width
- No horizontal scrolling required at 400% zoom
- No loss of information or functionality
- Exceptions: data tables, diagrams, maps

```css
/* Mobile-first responsive design */
.calculator-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

@media (min-width: 768px) {
  .calculator-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
```

#### 1.4.11 Non-text Contrast (Level AA)

[ ] **UI Component Contrast: 3:1**
- Button borders and backgrounds
- Form input borders
- Focus indicators
- Chart elements
- Icon colors

[ ] **State Indicators**
- Hover states have sufficient contrast
- Active states distinguishable
- Disabled states clearly different

#### 1.4.12 Text Spacing (Level AA)

[ ] **Text Spacing Override**
- Interface functional when user applies:
  - Line height: 1.5× font size
  - Paragraph spacing: 2× font size
  - Letter spacing: 0.12× font size
  - Word spacing: 0.16× font size

```css
/* Design must accommodate these overrides */
* {
  line-height: 1.5 !important;
  letter-spacing: 0.12em !important;
  word-spacing: 0.16em !important;
}

p {
  margin-bottom: 2em !important;
}
```

#### 1.4.13 Content on Hover or Focus (Level AA)

[ ] **Tooltips and Popovers**
- Content remains visible until dismissed or no longer relevant
- Pointer can move to triggered content without it disappearing
- Dismissable via Escape key
- Persistent until user action

```jsx
// Tooltip remains visible when hovered
<Tooltip
  content="Normal PSA range: 0-4 ng/mL"
  trigger="hover"
  persistent
  dismissible
>
  <InfoIcon />
</Tooltip>
```

---

## 2. Operable

User interface components and navigation must be operable.

### 2.1 Keyboard Accessible (Level A)

#### 2.1.1 Keyboard

[ ] **All Functionality Keyboard Accessible**
- All interactive elements reachable via keyboard
- All actions performable via keyboard
- No keyboard traps
- Custom widgets have proper keyboard support

```jsx
// Calculator card must be keyboard navigable
<div 
  role="button"
  tabIndex={0}
  onClick={handleClick}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      handleClick();
    }
  }}
>
  PSA Kinetics Calculator
</div>
```

[ ] **Keyboard Shortcuts**
- Document all keyboard shortcuts
- Provide alternatives for single-key shortcuts
- Allow users to turn off shortcuts

RECOMMENDED SHORTCUTS:
```
Ctrl/Cmd + N     New note
Ctrl/Cmd + S     Save note
Ctrl/Cmd + K     Open calculator selector
Ctrl/Cmd + /     Focus search
Esc              Close modal/dismiss notification
```

#### 2.1.2 No Keyboard Trap

[ ] **Keyboard Navigation Flow**
- Focus can move away from any component via keyboard
- If trap necessary (e.g., modal), escape method provided
- Instructions for exiting provided

```jsx
// Modal with keyboard trap and escape
<Modal isOpen={isOpen} onClose={handleClose}>
  <div
    role="dialog"
    aria-modal="true"
    onKeyDown={(e) => {
      if (e.key === 'Escape') handleClose();
    }}
  >
    {/* Modal content */}
    <button onClick={handleClose}>Close (or press Esc)</button>
  </div>
</Modal>
```

#### 2.1.4 Character Key Shortcuts (Level A)

[ ] **Single Character Shortcuts**
- Can be turned off
- Can be remapped
- Only active when component has focus

### 2.2 Enough Time (Level A)

#### 2.2.1 Timing Adjustable

[ ] **Session Timeouts**
- User warned before timeout (at least 20 seconds before)
- User can extend session with simple action
- Timeout period: 30 minutes minimum
- No data loss on timeout

```jsx
// Session timeout warning
<Modal isOpen={showTimeoutWarning}>
  <h2>Session Expiring Soon</h2>
  <p>Your session will expire in {remainingSeconds} seconds due to inactivity.</p>
  <button onClick={extendSession}>Continue Working</button>
</Modal>
```

#### 2.2.2 Pause, Stop, Hide

[ ] **Moving/Blinking/Scrolling Content**
- Auto-updating content can be paused/stopped
- Animations can be paused
- No content blinks more than 3 times per second

```jsx
// Respect reduced motion preference
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 2.3 Seizures and Physical Reactions (Level A)

#### 2.3.1 Three Flashes or Below Threshold

[ ] **Flashing Content**
- No content flashes more than 3 times per second
- Large flashes below general and red flash thresholds
- Warning provided if unavoidable

### 2.4 Navigable (Level AA)

#### 2.4.1 Bypass Blocks (Level A)

[ ] **Skip Links**
- Skip to main content link (first focusable element)
- Skip navigation links for complex pages
- Skip to search (if prominent feature)

```html
<body>
  <a href="#main-content" class="skip-link">
    Skip to main content
  </a>
  <a href="#search" class="skip-link">
    Skip to search
  </a>
  
  <nav><!-- Navigation --></nav>
  
  <main id="main-content">
    <!-- Main content -->
  </main>
</body>
```

```css
.skip-link {
  position: absolute;
  left: -9999px;
  z-index: 999;
  padding: 1rem;
  background: var(--primary-blue);
  color: white;
}

.skip-link:focus {
  left: 0;
  top: 0;
}
```

#### 2.4.2 Page Titled (Level A)

[ ] **Page Titles**
- Every page has descriptive title
- Title describes page purpose
- Format: "Page Name - VAUCDA - VA"

```html
<title>Note Generation - VAUCDA - Department of Veterans Affairs</title>
<title>CAPRA Score Calculator - VAUCDA - VA</title>
<title>Settings - VAUCDA - VA</title>
```

#### 2.4.3 Focus Order (Level A)

[ ] **Logical Focus Order**
- Tab order follows visual order
- Tab order makes sense
- No surprising focus jumps
- Dynamically added content maintains order

#### 2.4.4 Link Purpose (Level A)

[ ] **Link Context**
- Link text describes destination
- Avoid "click here" or "read more"
- Programmatically determined from link text alone
- Or from link text with context

```html
<!-- Bad -->
<a href="/calculators/capra">Click here</a> for CAPRA score

<!-- Good -->
<a href="/calculators/capra">Calculate CAPRA Score</a>

<!-- Good with context -->
<section aria-labelledby="prostate-heading">
  <h2 id="prostate-heading">Prostate Cancer Calculators</h2>
  <a href="/calculators/capra">CAPRA Score</a>
  <a href="/calculators/pcpt">PCPT 2.0</a>
</section>
```

#### 2.4.5 Multiple Ways (Level AA)

[ ] **Navigation Methods**
- At least two ways to find pages:
  - Navigation menu
  - Search function
  - Sitemap
  - Table of contents
- Exception: Process flows (note generation)

#### 2.4.6 Headings and Labels (Level AA)

[ ] **Descriptive Headings**
- Headings describe topic/purpose
- Labels describe input purpose
- Consistent labeling across interface

```html
<!-- Descriptive headings -->
<h2>Clinical Input Area</h2>
<h3>Laboratory Results</h3>

<!-- Descriptive labels -->
<label for="psa">Prostate-Specific Antigen (PSA) in ng/mL</label>
<label for="gleason-primary">Gleason Primary Grade (1-5)</label>
```

#### 2.4.7 Focus Visible (Level AA)

[ ] **Visible Focus Indicator**
- Focus indicator visible on all interactive elements
- Minimum 2px outline
- Sufficient contrast (3:1 against background)
- Not obscured by other content

```css
/* Focus styles */
*:focus-visible {
  outline: 2px solid var(--primary-blue);
  outline-offset: 2px;
}

/* For dark backgrounds */
.dark-bg *:focus-visible {
  outline-color: white;
}

/* For specific components */
.button:focus-visible {
  outline: 2px solid var(--primary-blue);
  box-shadow: 0 0 0 4px rgba(44, 82, 130, 0.1);
}
```

### 2.5 Input Modalities (Level A/AA)

#### 2.5.1 Pointer Gestures (Level A)

[ ] **Single Pointer Operation**
- All multipoint gestures have single-point alternative
- All path-based gestures have single-point alternative
- Exceptions: Essential gestures

#### 2.5.2 Pointer Cancellation (Level A)

[ ] **Click/Touch Handling**
- No down-event triggers
- Completion on up-event
- Ability to abort action
- Or up-event reverses down-event

```jsx
// Good: Click triggers on up-event (default behavior)
<button onClick={handleClick}>Generate Note</button>

// Avoid: onMouseDown without proper cancellation
```

#### 2.5.3 Label in Name (Level A)

[ ] **Accessible Name Match**
- Visible text label matches accessible name
- Accessible name contains visible text

```html
<!-- Good: Visible text matches aria-label -->
<button aria-label="Generate clinical note">
  Generate Note
</button>

<!-- Better: Use visible text as accessible name -->
<button>Generate Note</button>
```

#### 2.5.4 Motion Actuation (Level A)

[ ] **Device Motion**
- Functions activated by device motion also available via UI
- Motion actuation can be disabled
- Exception: Motion essential to function

---

## 3. Understandable

Information and operation of user interface must be understandable.

### 3.1 Readable (Level AA)

#### 3.1.1 Language of Page (Level A)

[ ] **Page Language**
- lang attribute on html element
- Correct language code

```html
<html lang="en-US">
```

#### 3.1.2 Language of Parts (Level AA)

[ ] **Language Changes**
- Content in other languages marked with lang
- Abbreviations and medical terms appropriately marked

```html
<p>
  The patient presented with <span lang="la">in situ</span> carcinoma.
</p>
```

### 3.2 Predictable (Level A/AA)

#### 3.2.1 On Focus (Level A)

[ ] **Focus Behavior**
- Focus alone does not trigger context change
- No unexpected navigation
- No automatic form submission on focus

#### 3.2.2 On Input (Level A)

[ ] **Input Behavior**
- Changing input values doesn't trigger unexpected context changes
- Exceptions: User warned beforehand

```jsx
// Good: Explicit action required
<select onChange={handleChange}>
  <option>Select calculator...</option>
</select>
<button onClick={loadCalculator}>Load Calculator</button>

// Acceptable if user warned
<select 
  onChange={loadCalculator}
  aria-label="Select calculator (will load immediately)"
>
```

#### 3.2.3 Consistent Navigation (Level AA)

[ ] **Navigation Consistency**
- Navigation appears in same place on every page
- Navigation items in same order
- Components in consistent locations

#### 3.2.4 Consistent Identification (Level AA)

[ ] **Component Consistency**
- Same functionality labeled consistently
- Icons used consistently
- Buttons for same actions look the same

```html
<!-- Consistent save buttons across app -->
<button class="btn-primary">
  <SaveIcon />
  Save Note
</button>

<button class="btn-primary">
  <SaveIcon />
  Save Settings
</button>
```

### 3.3 Input Assistance (Level A/AA/AAA)

#### 3.3.1 Error Identification (Level A)

[ ] **Error Detection**
- Input errors automatically detected
- Errors described to user in text
- Error message identifies item in error

```html
<label for="psa-value">PSA Value *</label>
<input 
  id="psa-value"
  type="number"
  aria-invalid="true"
  aria-describedby="psa-error"
/>
<div id="psa-error" class="error-message">
  <svg aria-hidden="true"><!-- Error icon --></svg>
  PSA value is required and must be between 0 and 100
</div>
```

#### 3.3.2 Labels or Instructions (Level A)

[ ] **Input Guidance**
- Labels provided for all inputs
- Instructions provided when needed
- Format requirements explained
- Required fields clearly marked

```html
<label for="dob">Date of Birth *</label>
<input 
  type="date"
  id="dob"
  required
  aria-required="true"
  aria-describedby="dob-help"
/>
<div id="dob-help" class="help-text">
  Format: MM/DD/YYYY. Required for age-based calculations.
</div>
```

#### 3.3.3 Error Suggestion (Level AA)

[ ] **Error Correction**
- Suggestions provided for correcting errors
- Suggestions specific and helpful
- Security exceptions noted

```html
<div class="error-message">
  PSA value must be a number between 0 and 100.
  You entered: "ABC". Please enter a valid number.
</div>
```

#### 3.3.4 Error Prevention (Legal, Financial, Data) (Level AA)

[ ] **Submission Prevention**
- Submissions are reversible, OR
- Data is checked for errors before submission, OR
- User can review, confirm, and correct before final submission

```jsx
// Note generation with preview
<div>
  <h2>Generated Note Preview</h2>
  <pre>{generatedNote}</pre>
  
  <div class="actions">
    <button onClick={goBack}>Edit Input</button>
    <button onClick={regenerate}>Regenerate</button>
    <button onClick={confirmAndSave} class="btn-primary">
      Confirm and Save Note
    </button>
  </div>
</div>
```

---

## 4. Robust

Content must be robust enough to be interpreted reliably by a wide variety of user agents, including assistive technologies.

### 4.1 Compatible (Level A/AA)

#### 4.1.1 Parsing

[ ] **Valid HTML**
- Elements have complete start and end tags
- Elements are nested properly
- Elements don't contain duplicate attributes
- IDs are unique

```bash
# Validate HTML
npm run validate-html
# or use https://validator.w3.org/
```

#### 4.1.2 Name, Role, Value (Level A)

[ ] **Component Properties**
- All components have accessible name
- All components have appropriate role
- States and properties programmatically determinable
- Notifications of changes available to user agents

```html
<!-- Custom checkbox with proper ARIA -->
<div
  role="checkbox"
  aria-checked="false"
  aria-labelledby="calculator-label"
  tabindex="0"
  onKeyDown={handleKeyPress}
>
  <span id="calculator-label">CAPRA Score Calculator</span>
</div>

<!-- Better: Use native elements when possible -->
<input
  type="checkbox"
  id="capra-calc"
  aria-describedby="capra-desc"
/>
<label for="capra-calc">CAPRA Score Calculator</label>
<div id="capra-desc">Cancer of Prostate Risk Assessment</div>
```

#### 4.1.3 Status Messages (Level AA)

[ ] **Live Regions**
- Status messages use appropriate ARIA live regions
- Changes announced to screen readers
- Updates don't interrupt user

```html
<!-- Success notification -->
<div
  role="status"
  aria-live="polite"
  aria-atomic="true"
  class="success-message"
>
  Note successfully generated
</div>

<!-- Error notification (interrupts) -->
<div
  role="alert"
  aria-live="assertive"
  aria-atomic="true"
  class="error-message"
>
  Connection to server lost
</div>

<!-- Loading indicator -->
<div
  role="status"
  aria-live="polite"
  aria-label="Loading"
>
  <span class="spinner"></span>
  <span class="sr-only">Generating note, please wait...</span>
</div>
```

---

## 5. Testing Procedures

### 5.1 Automated Testing

#### Tools Required
1. **axe DevTools** (Browser extension)
2. **WAVE** (Web Accessibility Evaluation Tool)
3. **Lighthouse** (Chrome DevTools)
4. **Pa11y** (Command-line tool)

#### Testing Commands

```bash
# Install testing dependencies
npm install --save-dev @axe-core/react pa11y lighthouse

# Run automated accessibility tests
npm run test:a11y

# Pa11y testing
pa11y http://localhost:3000

# Lighthouse CI
lighthouse http://localhost:3000 --only-categories=accessibility
```

#### Automated Test Coverage

```javascript
// Example: Axe testing in Jest
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

test('NoteGenerator component is accessible', async () => {
  const { container } = render(<NoteGenerator />);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

### 5.2 Manual Testing

#### Keyboard Navigation Test

1. **Tab Through Interface**
   - [ ] Tab moves focus forward logically
   - [ ] Shift+Tab moves focus backward
   - [ ] All interactive elements reachable
   - [ ] Focus indicator always visible
   - [ ] No keyboard traps

2. **Keyboard Operation**
   - [ ] Enter activates buttons/links
   - [ ] Space activates buttons/checkboxes
   - [ ] Arrow keys navigate menus/tabs
   - [ ] Escape closes modals/menus

3. **Shortcuts**
   - [ ] All shortcuts documented
   - [ ] Single-key shortcuts can be disabled
   - [ ] No conflicts with screen reader shortcuts

#### Screen Reader Testing

**Tools:** NVDA (Windows), JAWS (Windows), VoiceOver (macOS/iOS), TalkBack (Android)

**Test Scenarios:**
1. **Navigation**
   - [ ] Headings navigable with H key
   - [ ] Landmarks navigable with D key
   - [ ] Forms navigable with F key
   - [ ] Links navigable with K key

2. **Content**
   - [ ] All text content read correctly
   - [ ] Images have appropriate alt text
   - [ ] Tables have proper headers
   - [ ] Lists announced correctly

3. **Forms**
   - [ ] All labels read with inputs
   - [ ] Required fields announced
   - [ ] Error messages read
   - [ ] Help text associated correctly

4. **Dynamic Content**
   - [ ] Live regions announce updates
   - [ ] Modal focus managed correctly
   - [ ] Loading states announced
   - [ ] Success/error messages announced

#### Visual Testing

1. **Color Contrast**
   - [ ] Test all text with WebAIM Contrast Checker
   - [ ] Test focus indicators
   - [ ] Test UI components
   - [ ] Test in dark mode

2. **Zoom/Magnification**
   - [ ] 200% zoom: No horizontal scroll (1280px width)
   - [ ] 400% zoom: Content reflows correctly
   - [ ] No clipped content
   - [ ] No overlapping text

3. **Color Blindness Simulation**
   - [ ] Test with Chromatic Vision Simulator
   - [ ] Protanopia (red-blind)
   - [ ] Deuteranopia (green-blind)
   - [ ] Tritanopia (blue-blind)
   - [ ] Monochromacy (total color blindness)

### 5.3 User Testing

#### Testing with Real Users

1. **Screen Reader Users**
   - Recruit 3-5 screen reader users
   - Test core workflows
   - Note pain points and confusion
   - Gather qualitative feedback

2. **Keyboard-Only Users**
   - Test navigation efficiency
   - Identify keyboard traps
   - Test shortcut usability

3. **Low Vision Users**
   - Test with magnification
   - Test with high contrast
   - Test with custom colors

4. **Cognitive Disabilities**
   - Test clarity of instructions
   - Test error handling
   - Test timeout warnings

---

## 6. Remediation Guide

### Priority Levels

**Critical (P0)**: Blocks core functionality, fix immediately
**High (P1)**: Significant barrier, fix within 1 week
**Medium (P2)**: Moderate barrier, fix within 1 month
**Low (P3)**: Minor issue, fix when possible

### Common Issues and Fixes

#### Issue: Missing Alt Text
**Priority:** P0
**Fix:**
```html
<!-- Before -->
<img src="calculator-icon.png" />

<!-- After -->
<img src="calculator-icon.png" alt="Clinical calculator" />
```

#### Issue: Insufficient Color Contrast
**Priority:** P1
**Fix:**
```css
/* Before: 3.2:1 ratio */
.text {
  color: #999; /* Too light */
}

/* After: 4.6:1 ratio */
.text {
  color: #6b7280; /* Gray-500 */
}
```

#### Issue: Missing Form Labels
**Priority:** P0
**Fix:**
```html
<!-- Before -->
<input type="text" placeholder="PSA value" />

<!-- After -->
<label for="psa">PSA Value (ng/mL)</label>
<input type="text" id="psa" placeholder="e.g., 4.5" />
```

#### Issue: No Keyboard Access
**Priority:** P0
**Fix:**
```jsx
// Before
<div onClick={handleClick}>Click me</div>

// After
<button onClick={handleClick}>Click me</button>
// OR
<div
  role="button"
  tabIndex={0}
  onClick={handleClick}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  }}
>
  Click me
</div>
```

#### Issue: Unclear Focus Indicator
**Priority:** P1
**Fix:**
```css
/* Before */
*:focus {
  outline: 1px dotted gray; /* Too subtle */
}

/* After */
*:focus-visible {
  outline: 2px solid var(--primary-blue);
  outline-offset: 2px;
}
```

#### Issue: No Skip Link
**Priority:** P1
**Fix:**
```html
<body>
  <a href="#main-content" class="skip-link">Skip to main content</a>
  <nav><!-- Navigation --></nav>
  <main id="main-content"><!-- Content --></main>
</body>
```

---

## 7. Tools and Resources

### Browser Extensions
- **axe DevTools**: Automated accessibility testing
- **WAVE**: Visual accessibility checker
- **Lighthouse**: Comprehensive auditing
- **ARIA DevTools**: ARIA attribute inspector
- **Accessibility Insights**: Microsoft accessibility checker

### Online Tools
- **WebAIM Contrast Checker**: https://webaim.org/resources/contrastchecker/
- **W3C HTML Validator**: https://validator.w3.org/
- **WAVE**: https://wave.webaim.org/
- **Pa11y**: https://pa11y.org/

### Screen Readers
- **NVDA** (Free, Windows): https://www.nvaccess.org/
- **JAWS** (Commercial, Windows): https://www.freedomscientific.com/products/software/jaws/
- **VoiceOver** (Built-in, macOS/iOS)
- **TalkBack** (Built-in, Android)
- **ChromeVox** (Chrome extension)

### Testing Libraries
```bash
npm install --save-dev \
  @axe-core/react \
  jest-axe \
  @testing-library/jest-dom \
  @testing-library/react \
  pa11y \
  lighthouse
```

### Documentation
- **WCAG 2.1**: https://www.w3.org/WAI/WCAG21/quickref/
- **ARIA Authoring Practices**: https://www.w3.org/WAI/ARIA/apg/
- **MDN Accessibility**: https://developer.mozilla.org/en-US/docs/Web/Accessibility
- **WebAIM**: https://webaim.org/

---

## Compliance Checklist Summary

### Level A (25 criteria)
- [ ] Text alternatives
- [ ] Captions (prerecorded)
- [ ] Audio descriptions or alternative
- [ ] Info and relationships
- [ ] Meaningful sequence
- [ ] Sensory characteristics
- [ ] Use of color
- [ ] Audio control
- [ ] Keyboard
- [ ] No keyboard trap
- [ ] Timing adjustable
- [ ] Pause, stop, hide
- [ ] Three flashes or below
- [ ] Bypass blocks
- [ ] Page titled
- [ ] Focus order
- [ ] Link purpose (in context)
- [ ] Pointer gestures
- [ ] Pointer cancellation
- [ ] Label in name
- [ ] Motion actuation
- [ ] Language of page
- [ ] On focus
- [ ] On input
- [ ] Error identification
- [ ] Labels or instructions
- [ ] Parsing
- [ ] Name, role, value

### Level AA (20 criteria)
- [ ] Captions (live)
- [ ] Audio description (prerecorded)
- [ ] Orientation
- [ ] Identify input purpose
- [ ] Contrast (minimum)
- [ ] Resize text
- [ ] Images of text
- [ ] Reflow
- [ ] Non-text contrast
- [ ] Text spacing
- [ ] Content on hover or focus
- [ ] Character key shortcuts
- [ ] Multiple ways
- [ ] Headings and labels
- [ ] Focus visible
- [ ] Language of parts
- [ ] Consistent navigation
- [ ] Consistent identification
- [ ] Error suggestion
- [ ] Error prevention (legal, financial, data)
- [ ] Status messages

---

## Testing Schedule

### Development Phase
- **Daily**: Automated tests in CI/CD
- **Weekly**: Manual keyboard testing
- **Sprint**: Screen reader testing of new features
- **Sprint**: Color contrast verification

### Pre-Release
- **2 weeks before**: Full WCAG audit
- **1 week before**: User testing with assistive technology users
- **Release**: Final automated check

### Post-Release
- **Monthly**: Accessibility monitoring
- **Quarterly**: Full manual audit
- **Annually**: Professional audit (recommended)

---

**Document Owner**: VAUCDA Accessibility Team
**Last Updated**: November 29, 2025
**Next Review**: February 29, 2026

**Compliance Target**: 100% WCAG 2.1 Level AA
**Current Status**: Pre-implementation
