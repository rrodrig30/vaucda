# VAUCDA Style Guide
## Visual Design & Implementation Guidelines

Version: 1.0
Date: November 29, 2025
For: Frontend Developers & Designers

---

## Purpose

This style guide provides practical implementation guidelines, code examples, and visual design principles for building the VAUCDA frontend. Use this as your day-to-day reference alongside the Design System document.

---

## Table of Contents

1. [Visual Design Principles](#visual-design-principles)
2. [Clinical UI Best Practices](#clinical-ui-best-practices)
3. [Component Usage Guidelines](#component-usage-guidelines)
4. [Layout Patterns](#layout-patterns)
5. [Do's and Don'ts](#dos-and-donts)
6. [Code Examples](#code-examples)

---

## Visual Design Principles

### 1. Clinical Clarity Above All

**Principle**: Medical interfaces must be instantly clear and unambiguous.

DO:
- Use high contrast for critical information
- Provide clear visual hierarchy
- Use ample white space for breathing room
- Display lab values in monospace font with units

DON'T:
- Use decorative elements that distract
- Rely on color alone to convey information
- Use low contrast for clinical data
- Overcrowd the interface with information

**Example:**
```jsx
// Good: Clear lab value display
<div className="flex items-baseline gap-2">
  <span className="font-mono text-lg font-semibold">4.5</span>
  <span className="text-sm text-gray-600">ng/mL</span>
  <span className="text-sm text-gray-500">(Normal: 0-4)</span>
</div>

// Bad: Unclear presentation
<div>4.5ng/mL (0-4)</div>
```

### 2. Efficiency-Focused Design

**Principle**: Reduce clicks, reduce cognitive load, increase speed.

DO:
- Place common actions prominently
- Use keyboard shortcuts for power users
- Provide smart defaults
- Enable rapid data entry

DON'T:
- Hide common actions in menus
- Require unnecessary confirmations
- Force navigation through multiple pages
- Make users repeat data entry

**Example:**
```jsx
// Good: One-click calculator access with keyboard shortcut
<div className="grid grid-cols-3 gap-4">
  {calculators.map((calc, idx) => (
    <CalculatorCard
      key={calc.id}
      calculator={calc}
      onClick={() => openCalculator(calc.id)}
      shortcut={idx < 9 ? `Ctrl+${idx + 1}` : null}
    />
  ))}
</div>

// Bad: Multiple steps to access
<Menu>
  <MenuItem onClick={openCalculators}>
    Calculators
  </MenuItem>
</Menu>
{showCalculators && (
  <Modal>
    <List>
      {/* Calculator list */}
    </List>
  </Modal>
)}
```

### 3. Professional Medical Aesthetics

**Principle**: Convey trust and authority through design.

DO:
- Use professional blue color palette
- Maintain clean, structured layouts
- Use medical-grade typography
- Apply subtle, purposeful animations

DON'T:
- Use bright, playful colors
- Use decorative fonts
- Add unnecessary animations
- Use consumer app patterns

**Color Usage:**
```jsx
// Good: Professional color application
<button className="bg-primary-600 text-white hover:bg-primary-500">
  Generate Clinical Note
</button>

<button className="bg-medical-600 text-white hover:bg-medical-500">
  Run Calculator
</button>

// Bad: Inappropriate colors
<button className="bg-pink-500 text-white">
  Generate Note
</button>
```

### 4. Data-First Information Display

**Principle**: Present data in scannable, structured formats.

DO:
- Use tables for structured data
- Align numbers right for easy comparison
- Highlight critical values
- Provide visual indicators for trends

DON'T:
- Use prose for tabular data
- Mix alignment in columns
- Bury critical values in text
- Show data without context

**Example:**
```jsx
// Good: Structured data display
<table className="w-full">
  <thead className="bg-gray-50">
    <tr>
      <th className="text-left">Date</th>
      <th className="text-right">PSA (ng/mL)</th>
      <th className="text-right">Change</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>2024-11-01</td>
      <td className="text-right font-mono">4.5</td>
      <td className="text-right text-warning-600">+0.5</td>
    </tr>
  </tbody>
</table>

// Bad: Unstructured presentation
<p>On 2024-11-01 PSA was 4.5 ng/mL which was +0.5 from previous</p>
```

---

## Clinical UI Best Practices

### Lab Values & Clinical Data

**Always Include:**
1. Value (with proper precision)
2. Unit of measurement
3. Reference range
4. Timestamp (when relevant)
5. Visual indicator for abnormal values

```jsx
<div className="space-y-2">
  <div className="flex items-baseline justify-between">
    <span className="font-medium">Prostate-Specific Antigen</span>
    <time className="text-sm text-gray-500">2024-11-29</time>
  </div>
  
  <div className="flex items-baseline gap-2">
    <span className={cn(
      "font-mono text-2xl font-semibold",
      value > 4 ? "text-warning-600" : "text-gray-900"
    )}>
      {value.toFixed(1)}
    </span>
    <span className="text-sm text-gray-600">ng/mL</span>
  </div>
  
  <div className="text-sm text-gray-500">
    Reference: 0-4 ng/mL
  </div>
  
  {value > 4 && (
    <div className="flex items-center gap-2 text-warning-900">
      <AlertIcon className="w-4 h-4" />
      <span className="text-sm">Above reference range</span>
    </div>
  )}
</div>
```

### Calculator Interfaces

**Structure:**
```
┌─────────────────────────────────────────┐
│ Calculator Name                         │
│ Brief description                       │
├─────────────────────────────────────────┤
│ INPUTS                                  │
│ ┌─────────────────────────────────┐     │
│ │ Label (with units)      [Value] │     │
│ │ Helper text: range              │     │
│ └─────────────────────────────────┘     │
├─────────────────────────────────────────┤
│ RESULTS                                 │
│ Score: 42                               │
│ Risk Category: Intermediate             │
│ Interpretation text...                  │
├─────────────────────────────────────────┤
│ [Copy Results] [Export] [References]    │
└─────────────────────────────────────────┘
```

**Code Example:**
```jsx
<Card>
  <CardHeader>
    <h2 className="text-h2">CAPRA Score</h2>
    <p className="text-gray-600">
      Cancer of the Prostate Risk Assessment
    </p>
  </CardHeader>
  
  <CardBody>
    <section aria-labelledby="inputs-heading">
      <h3 id="inputs-heading" className="text-h4 mb-4">
        Clinical Inputs
      </h3>
      
      <div className="space-y-4">
        <FormField
          label="PSA (ng/mL)"
          type="number"
          value={psa}
          onChange={setPsa}
          min={0}
          max={100}
          helperText="Prostate-specific antigen value"
        />
        
        <FormField
          label="Gleason Primary Grade"
          type="select"
          value={gleason}
          onChange={setGleason}
          options={[3, 4, 5]}
        />
      </div>
    </section>
    
    {result && (
      <section 
        aria-labelledby="results-heading"
        className="mt-8 p-6 bg-gradient-prostate rounded-lg"
      >
        <h3 id="results-heading" className="text-h4 mb-4">
          Results
        </h3>
        
        <div className="mb-4">
          <div className="text-sm text-gray-600">CAPRA Score</div>
          <div className="text-4xl font-bold text-primary-600">
            {result.score}
          </div>
        </div>
        
        <div className="mb-4">
          <div className="text-sm text-gray-600">Risk Category</div>
          <Badge variant={result.riskLevel}>
            {result.riskCategory}
          </Badge>
        </div>
        
        <p className="text-sm text-gray-700">
          {result.interpretation}
        </p>
      </section>
    )}
  </CardBody>
  
  <CardFooter>
    <button className="btn-secondary">
      View References
    </button>
    <button className="btn-primary">
      Add to Note
    </button>
  </CardFooter>
</Card>
```

### Note Display

**Principles:**
- Monospace for structured data
- Clear section headers
- Adequate spacing for scanning
- Syntax highlighting for important elements

```jsx
<div className="max-w-4xl mx-auto">
  <article className="prose prose-lg">
    <section>
      <h2 className="medical-heading">Chief Complaint</h2>
      <p>{note.chiefComplaint}</p>
    </section>
    
    <section>
      <h2 className="medical-heading">History of Present Illness</h2>
      <p>{note.hpi}</p>
    </section>
    
    <section>
      <h2 className="medical-heading">Physical Examination</h2>
      <h3>Genitourinary</h3>
      <pre className="lab-value bg-gray-50 p-4 rounded">
        {note.guExam}
      </pre>
    </section>
    
    <section>
      <h2 className="medical-heading">Laboratory Results</h2>
      <table>
        <thead>
          <tr>
            <th>Test</th>
            <th>Value</th>
            <th>Reference</th>
          </tr>
        </thead>
        <tbody>
          {note.labs.map(lab => (
            <tr key={lab.test}>
              <td>{lab.test}</td>
              <td className="font-mono text-right">{lab.value}</td>
              <td className="text-sm text-gray-500">{lab.reference}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
    
    <section>
      <h2 className="medical-heading">Assessment and Plan</h2>
      <ol>
        {note.assessmentPlan.map((item, idx) => (
          <li key={idx}>{item}</li>
        ))}
      </ol>
    </section>
  </article>
</div>
```

---

## Component Usage Guidelines

### Buttons

#### When to Use Each Button Type

**Primary Button** (`.btn-primary`):
- Main action on a page (only one per view)
- Note generation, Save, Submit
- High-consequence actions

**Medical Button** (`.btn-medical`):
- Medical/clinical-specific actions
- Run calculator, Generate report
- Clinical decision support actions

**Secondary Button** (`.btn-secondary`):
- Alternative actions
- Cancel, Reset, Back
- Less important actions

**Tertiary/Ghost Button**:
- Low-priority actions
- View more, Expand, Show details
- Navigation within sections

**Example Usage:**
```jsx
// Note generation page - single primary action
<div className="flex gap-3 justify-end">
  <button className="btn-secondary" onClick={handleReset}>
    Clear Input
  </button>
  <button className="btn-primary" onClick={handleGenerate}>
    Generate Note
  </button>
</div>

// Calculator - medical action
<div className="flex gap-3 justify-end">
  <button className="btn-ghost" onClick={showReferences}>
    View References
  </button>
  <button className="btn-medical" onClick={calculate}>
    Calculate Score
  </button>
</div>
```

### Cards

#### Standard Card
Use for grouping related content, calculators, results display.

```jsx
<Card>
  <CardHeader>
    <h3>PSA Kinetics</h3>
    <p className="text-sm text-gray-600">
      Calculate PSA velocity and doubling time
    </p>
  </CardHeader>
  
  <CardBody>
    {/* Content */}
  </CardBody>
  
  <CardFooter>
    {/* Actions */}
  </CardFooter>
</Card>
```

#### Interactive Card
Use for selectable items (calculator selection, template selection).

```jsx
<Card 
  className="cursor-pointer hover:shadow-lg transition-all"
  onClick={handleSelect}
  onKeyDown={handleKeyPress}
  tabIndex={0}
  role="button"
  aria-pressed={isSelected}
>
  {/* Content */}
</Card>
```

#### Gradient Cards
Use for category differentiation.

```jsx
<Card className="bg-gradient-prostate">
  <h3>Prostate Cancer Calculators</h3>
  <div className="grid grid-cols-2 gap-4">
    {/* Calculator list */}
  </div>
</Card>
```

### Forms

#### Form Field Anatomy
```jsx
<div className="form-field">
  <label htmlFor="input-id" className="form-label">
    Label Text *
  </label>
  
  <input
    id="input-id"
    type="text"
    className="form-input"
    required
    aria-required="true"
    aria-describedby="input-help input-error"
  />
  
  <div id="input-help" className="form-help">
    Helper text explaining the input
  </div>
  
  {error && (
    <div id="input-error" className="form-error">
      <AlertIcon />
      {error}
    </div>
  )}
</div>
```

#### Validation States
```jsx
// Normal state
<input className="border-gray-300 focus:border-primary-600" />

// Error state
<input 
  className="border-error-500 bg-error-50 focus:border-error-600"
  aria-invalid="true"
/>

// Success state
<input 
  className="border-success-500 bg-success-50"
  aria-invalid="false"
/>

// Disabled state
<input 
  className="bg-gray-100 text-gray-500 cursor-not-allowed"
  disabled
/>
```

### Alerts & Notifications

#### Inline Alerts
```jsx
// Success
<Alert variant="success">
  <CheckIcon />
  <span>Note successfully generated and saved</span>
</Alert>

// Warning
<Alert variant="warning">
  <AlertIcon />
  <span>Session will expire in 5 minutes</span>
  <button onClick={extendSession}>Extend Session</button>
</Alert>

// Error
<Alert variant="error">
  <XIcon />
  <span>Failed to connect to server</span>
  <button onClick={retry}>Retry</button>
</Alert>

// Info
<Alert variant="info">
  <InfoIcon />
  <span>New calculator available: Renal Mass Score</span>
</Alert>
```

#### Toast Notifications
```jsx
// Programmatic usage
toast.success('Note saved successfully');
toast.error('Connection failed');
toast.warning('Unsaved changes will be lost');
toast.info('Update available');

// With action
toast.success('Note saved', {
  action: {
    label: 'View',
    onClick: () => navigateToNote()
  }
});
```

---

## Layout Patterns

### Page Layout Structure

```jsx
<div className="min-h-screen bg-gray-50">
  {/* Header */}
  <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
    <div className="max-w-7xl mx-auto px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <img src="/logo.svg" alt="VA" className="h-12" />
          <h1 className="text-xl font-semibold">VAUCDA</h1>
        </div>
        
        <nav className="flex items-center gap-6">
          <NavLink to="/notes">Notes</NavLink>
          <NavLink to="/calculators">Calculators</NavLink>
          <NavLink to="/search">Evidence</NavLink>
        </nav>
        
        <div className="flex items-center gap-4">
          <button className="btn-ghost">
            <SettingsIcon />
          </button>
          <UserMenu />
        </div>
      </div>
    </div>
  </header>
  
  {/* Main Content */}
  <main className="max-w-7xl mx-auto px-6 py-8">
    {children}
  </main>
  
  {/* Footer (optional) */}
  <footer className="bg-white border-t border-gray-200 mt-auto">
    <div className="max-w-7xl mx-auto px-6 py-4">
      <p className="text-sm text-gray-600">
        Department of Veterans Affairs
      </p>
    </div>
  </footer>
</div>
```

### Two-Column Layout (Input/Output)

```jsx
<div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
  {/* Input Panel */}
  <section aria-labelledby="input-heading">
    <h2 id="input-heading" className="text-h2 mb-6">
      Clinical Input
    </h2>
    
    <Card>
      <CardBody>
        <textarea 
          className="w-full h-96 p-4 font-mono"
          placeholder="Paste clinical data..."
        />
      </CardBody>
    </Card>
  </section>
  
  {/* Output Panel */}
  <section aria-labelledby="output-heading">
    <h2 id="output-heading" className="text-h2 mb-6">
      Generated Note
    </h2>
    
    <Card>
      <CardBody>
        {isLoading ? (
          <SkeletonLoader />
        ) : (
          <div className="prose">{generatedNote}</div>
        )}
      </CardBody>
    </Card>
  </section>
</div>
```

### Dashboard Grid

```jsx
<div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
  {/* Quick Actions */}
  <Card className="md:col-span-2">
    <CardHeader>
      <h2>Quick Actions</h2>
    </CardHeader>
    <CardBody>
      <div className="grid grid-cols-2 gap-4">
        <QuickAction icon={<DocumentIcon />} label="New Note" />
        <QuickAction icon={<CalculatorIcon />} label="Calculators" />
        <QuickAction icon={<SearchIcon />} label="Evidence Search" />
        <QuickAction icon={<SettingsIcon />} label="Settings" />
      </div>
    </CardBody>
  </Card>
  
  {/* Recent Activity */}
  <Card>
    <CardHeader>
      <h2>Recent Activity</h2>
    </CardHeader>
    <CardBody>
      <RecentActivityList />
    </CardBody>
  </Card>
  
  {/* Favorite Calculators */}
  <Card className="md:col-span-3">
    <CardHeader>
      <h2>Favorite Calculators</h2>
    </CardHeader>
    <CardBody>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {favoriteCalculators.map(calc => (
          <CalculatorCard key={calc.id} calculator={calc} />
        ))}
      </div>
    </CardBody>
  </Card>
</div>
```

---

## Do's and Don'ts

### Color

DO:
- Use primary blue (#2c5282) for main actions
- Use medical teal (#0d9488) for clinical actions
- Provide sufficient contrast (4.5:1 minimum)
- Use color + icon for status indicators

DON'T:
- Use color as the only means of communication
- Use red and green together without labels
- Use low-contrast color combinations
- Use more than 3 colors in a single component

### Typography

DO:
- Use 16px minimum for body text
- Use monospace for lab values and clinical data
- Maintain consistent heading hierarchy
- Use adequate line spacing (1.5+)

DON'T:
- Use font sizes smaller than 14px
- Skip heading levels (h1 → h3)
- Use decorative fonts for clinical content
- Use all caps for long text

### Spacing

DO:
- Use 8px base grid consistently
- Provide breathing room between sections (24px+)
- Group related elements closely
- Use consistent padding in components

DON'T:
- Use arbitrary spacing values
- Overcrowd the interface
- Use inconsistent spacing patterns
- Forget mobile spacing considerations

### Interaction

DO:
- Provide visual feedback immediately
- Show loading states for async operations
- Confirm destructive actions
- Support keyboard navigation

DON'T:
- Make users wait without feedback
- Hide important actions in menus
- Use hover-only interfaces
- Ignore keyboard users

---

## Code Examples

### Complete Component Example

```jsx
import React, { useState } from 'react';
import { Card, CardHeader, CardBody, CardFooter } from '@/components/ui/Card';
import { FormField } from '@/components/ui/FormField';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';

export function CAPRACalculator() {
  const [inputs, setInputs] = useState({
    psa: '',
    age: '',
    gleason: '',
    clinicalStage: '',
    percentPositiveBiopsies: ''
  });
  
  const [result, setResult] = useState(null);
  const [errors, setErrors] = useState({});
  
  const calculate = () => {
    // Validation
    const newErrors = {};
    if (!inputs.psa || inputs.psa < 0) {
      newErrors.psa = 'PSA value is required and must be positive';
    }
    // ... more validation
    
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    
    // Calculate CAPRA score
    let score = 0;
    
    // PSA component
    if (inputs.psa > 6 && inputs.psa <= 10) score += 1;
    else if (inputs.psa > 10 && inputs.psa <= 20) score += 2;
    else if (inputs.psa > 20) score += 3;
    
    // Age component
    if (inputs.age < 50) score += 0;
    else score += 1;
    
    // ... more scoring logic
    
    // Determine risk category
    let riskCategory, interpretation;
    if (score <= 2) {
      riskCategory = 'Low Risk';
      interpretation = '5-year progression-free survival approximately 85%';
    } else if (score <= 5) {
      riskCategory = 'Intermediate Risk';
      interpretation = '5-year progression-free survival approximately 65%';
    } else {
      riskCategory = 'High Risk';
      interpretation = '5-year progression-free survival approximately 40%';
    }
    
    setResult({
      score,
      riskCategory,
      interpretation
    });
  };
  
  return (
    <Card className="max-w-4xl mx-auto">
      <CardHeader>
        <h2 className="text-h2 text-primary-600">
          CAPRA Score Calculator
        </h2>
        <p className="text-gray-600 mt-2">
          Cancer of the Prostate Risk Assessment - predicts disease 
          recurrence after radical prostatectomy
        </p>
      </CardHeader>
      
      <CardBody>
        <section aria-labelledby="inputs-heading" className="space-y-6">
          <h3 id="inputs-heading" className="text-h3">
            Clinical Inputs
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <FormField
              label="PSA (ng/mL)"
              type="number"
              value={inputs.psa}
              onChange={(e) => setInputs({...inputs, psa: e.target.value})}
              min={0}
              step={0.1}
              required
              helperText="Prostate-specific antigen level"
              error={errors.psa}
            />
            
            <FormField
              label="Age (years)"
              type="number"
              value={inputs.age}
              onChange={(e) => setInputs({...inputs, age: e.target.value})}
              min={18}
              max={120}
              required
              helperText="Age at diagnosis"
              error={errors.age}
            />
            
            <FormField
              label="Gleason Primary Grade"
              type="select"
              value={inputs.gleason}
              onChange={(e) => setInputs({...inputs, gleason: e.target.value})}
              required
              options={[
                { value: '3', label: '3' },
                { value: '4', label: '4' },
                { value: '5', label: '5' }
              ]}
              error={errors.gleason}
            />
            
            <FormField
              label="Clinical Stage"
              type="select"
              value={inputs.clinicalStage}
              onChange={(e) => setInputs({...inputs, clinicalStage: e.target.value})}
              required
              options={[
                { value: 'T1', label: 'T1 (Non-palpable)' },
                { value: 'T2', label: 'T2 (Palpable, confined)' },
                { value: 'T3', label: 'T3 (Extension beyond capsule)' }
              ]}
              error={errors.clinicalStage}
            />
            
            <FormField
              label="Percent Positive Biopsies (%)"
              type="number"
              value={inputs.percentPositiveBiopsies}
              onChange={(e) => setInputs({...inputs, percentPositiveBiopsies: e.target.value})}
              min={0}
              max={100}
              step={1}
              required
              helperText="Percentage of biopsy cores positive for cancer"
              error={errors.percentPositiveBiopsies}
            />
          </div>
        </section>
        
        {result && (
          <section 
            aria-labelledby="results-heading"
            className="mt-8 p-6 bg-gradient-prostate rounded-lg"
          >
            <h3 id="results-heading" className="text-h3 mb-6">
              Results
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <div className="text-sm text-gray-600 mb-2">
                  CAPRA Score
                </div>
                <div className="text-5xl font-bold text-primary-600">
                  {result.score}
                </div>
                <div className="text-sm text-gray-500 mt-1">
                  Range: 0-10 points
                </div>
              </div>
              
              <div>
                <div className="text-sm text-gray-600 mb-2">
                  Risk Category
                </div>
                <Badge 
                  variant={
                    result.score <= 2 ? 'success' :
                    result.score <= 5 ? 'warning' : 'error'
                  }
                  size="lg"
                >
                  {result.riskCategory}
                </Badge>
              </div>
            </div>
            
            <Alert variant="info" className="mt-6">
              <div className="text-sm">
                <strong>Clinical Interpretation:</strong> {result.interpretation}
              </div>
            </Alert>
          </section>
        )}
      </CardBody>
      
      <CardFooter className="flex justify-between">
        <button 
          className="btn-secondary"
          onClick={() => {
            setInputs({
              psa: '', age: '', gleason: '', 
              clinicalStage: '', percentPositiveBiopsies: ''
            });
            setResult(null);
            setErrors({});
          }}
        >
          Reset
        </button>
        
        <div className="flex gap-3">
          <button className="btn-ghost">
            View References
          </button>
          <button 
            className="btn-medical"
            onClick={calculate}
          >
            Calculate Score
          </button>
        </div>
      </CardFooter>
    </Card>
  );
}
```

---

**Document Owner**: VAUCDA Design Team
**Last Updated**: November 29, 2025
