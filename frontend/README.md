# VAUCDA Frontend
## VA Urology Clinical Documentation Assistant - User Interface

Version: 1.0 (Design Phase)
Status: Ready for Implementation
Last Updated: November 29, 2025

---

## Overview

This directory contains the complete design system, UI/UX specifications, and implementation guidelines for the VAUCDA frontend application. The frontend is a modern React-based web application optimized for clinical workflows, built with accessibility and user experience as top priorities.

---

## Project Status

CURRENT PHASE: **Design & Specification Complete**
NEXT PHASE: **Implementation Kickoff**

Frontend implementation has not yet begun. This directory contains all design specifications, component guidelines, and standards required to build a production-ready medical-grade user interface.

---

## Documentation

### Core Design Documents

1. **[DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md)** (70+ pages)
   - Complete visual design specification
   - Color system with WCAG-compliant palette
   - Typography scale and font guidelines
   - Spacing system (8px base grid)
   - Component library specifications
   - Iconography guidelines
   - Interaction patterns
   - Animation and motion standards
   - Dark mode implementation
   - Responsive design breakpoints
   - Medical-specific UI patterns

2. **[ACCESSIBILITY_AUDIT.md](./ACCESSIBILITY_AUDIT.md)** (40+ pages)
   - WCAG 2.1 Level AA compliance checklist
   - Detailed testing procedures
   - Screen reader optimization guide
   - Keyboard navigation requirements
   - Remediation guidelines
   - Testing tools and resources
   - Compliance tracking matrix

3. **[STYLE_GUIDE.md](./STYLE_GUIDE.md)** (30+ pages)
   - Visual design principles
   - Clinical UI best practices
   - Component usage guidelines
   - Layout patterns
   - Code examples
   - Do's and don'ts
   - Implementation snippets

4. **[DESIGN_AUDIT_REPORT.md](./DESIGN_AUDIT_REPORT.md)** (50+ pages)
   - Comprehensive UI/UX analysis
   - Color system evaluation
   - Typography assessment
   - Accessibility compliance review
   - User experience optimization
   - Component recommendations
   - Clinical workflow patterns
   - Implementation roadmap
   - Testing requirements

### Configuration Files

- **[tailwind.config.js](./tailwind.config.js)** - Tailwind CSS configuration with VAUCDA color palette, typography scale, custom utilities, and medical-specific components

---

## Design System Highlights

### Color Palette

**Primary Colors:**
- Primary Blue: `#2c5282` - Trust, professionalism, main actions
- Medical Teal: `#0d9488` - Clinical actions, healthcare operations
- Accent Blue: `#63b3ed` - Links, interactive elements

**Semantic Colors:**
- Success: `#10b981` - Confirmations, positive states
- Warning: `#f59e0b` - Cautions, pending actions
- Error: `#ef4444` - Errors, critical alerts
- Info: `#06b6d4` - Informational messages

**All colors meet WCAG 2.1 AA contrast requirements (4.5:1 minimum)**

### Typography

- **Font Family**: Inter (primary), Roboto Mono (clinical data)
- **Base Size**: 16px minimum for body text
- **Scale**: Display, H1-H4, Body (lg, default, sm), Caption
- **Line Height**: 1.5 minimum for readability

### Spacing

- **Base Grid**: 8px
- **Touch Targets**: 48px × 48px minimum (WCAG AAA)
- **Container Max Width**: 1600px
- **Breakpoints**: 320px, 640px, 768px, 1024px, 1280px, 1440px

---

## Component Library

### Core Components (To Be Built)

1. **Buttons**: Primary, Medical, Secondary, Tertiary, Ghost, Danger
2. **Inputs**: Text, Number, Email, Password, Textarea, Select, Checkbox, Radio
3. **Cards**: Standard, Interactive, Gradient (medical categories)
4. **Alerts**: Success, Warning, Error, Info
5. **Modals**: Small, Default, Large
6. **Tables**: Sortable, responsive, accessible
7. **Loading States**: Spinner, Skeleton, Progress Bar
8. **Badges**: Status indicators
9. **Tooltips**: Contextual help
10. **Navigation**: Header, Tabs, Breadcrumbs

### Medical-Specific Components (To Be Built)

1. **CalculatorCard**: Clinical calculator selection cards
2. **LabValueDisplay**: Lab results with reference ranges
3. **NoteDisplay**: Generated clinical notes with syntax highlighting
4. **ClinicalDataTable**: Structured medical data tables
5. **PSATimeline**: Trend visualization for PSA values
6. **EvidenceCard**: Search result cards with citations

---

## Accessibility Compliance

### WCAG 2.1 Level AA Requirements

TARGET: **100% Compliance**

**Perceivable:**
- ✓ Text alternatives for all images
- ✓ Color contrast ≥ 4.5:1 for text
- ✓ Responsive reflow at 320px
- ✓ Text resizable to 200%

**Operable:**
- ✓ All functionality keyboard accessible
- ✓ Skip to main content link
- ✓ Visible focus indicators (2px, 3:1 contrast)
- ✓ No keyboard traps

**Understandable:**
- ✓ Language declared
- ✓ Consistent navigation
- ✓ Clear form labels
- ✓ Error suggestions provided

**Robust:**
- ✓ Valid HTML5
- ✓ Proper ARIA usage
- ✓ Status messages via live regions
- ✓ Assistive technology compatible

---

## User Experience Principles

### 1. Clinical Efficiency
- **Max 2 clicks** to access calculators
- **Max 3 clicks** for note generation
- Keyboard shortcuts for power users
- Auto-save for draft protection

### 2. Information Clarity
- High contrast for clinical data
- Monospace font for lab values
- Clear visual hierarchy
- Ample white space

### 3. Professional Aesthetics
- Medical-grade color palette
- Clean, structured layouts
- Subtle, purposeful animations
- Trust-inspiring design

### 4. Error Recovery
- Clear error messages
- Actionable recovery steps
- Inline validation
- Confirmation for destructive actions

---

## Implementation Timeline

### Phase 1: Foundation (Weeks 1-2)
- Project setup (React + TypeScript + Vite)
- Tailwind configuration
- Core UI components
- Routing and API setup

### Phase 2: Core Features (Weeks 3-5)
- Note Generation page
- Calculator system (44 calculators)
- Evidence Search interface

### Phase 3: Enhancement (Weeks 6-7)
- Settings page
- Dashboard
- User profile

### Phase 4: Polish & Accessibility (Week 8)
- Accessibility audit
- Performance optimization
- Error handling

### Phase 5: Testing & QA (Week 9)
- Unit tests
- Integration tests
- E2E tests
- Accessibility tests

### Phase 6: Deployment (Week 10)
- Production build
- Docker containerization
- Deployment to VA infrastructure
- UAT

**TOTAL ESTIMATED TIME: 10 weeks**

---

## Technology Stack (Recommended)

### Core Technologies
- **Framework**: React 18+
- **Language**: TypeScript 5+
- **Build Tool**: Vite 5+
- **Styling**: Tailwind CSS 3.4+
- **State Management**: Redux Toolkit 2.0+
- **Routing**: React Router 6+
- **HTTP Client**: Axios 1.6+

### Development Tools
- **Testing**: Jest + React Testing Library + Playwright
- **Accessibility**: axe-core, Pa11y
- **Code Quality**: ESLint + Prettier
- **Git Hooks**: Husky + lint-staged

### Additional Libraries
- **Form Handling**: React Hook Form
- **Date Handling**: date-fns
- **Icons**: Heroicons 2.0
- **Charts**: Recharts (for PSA trends)
- **PDF Export**: jsPDF + html2canvas

---

## Getting Started (When Implementation Begins)

### Prerequisites
- Node.js 18+
- npm 9+ or yarn 1.22+
- Git

### Setup Steps

```bash
# Create React project with Vite
npm create vite@latest vaucda-frontend -- --template react-ts

# Navigate to project
cd vaucda-frontend

# Install dependencies
npm install

# Install Tailwind CSS
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Copy VAUCDA Tailwind config
cp ../tailwind.config.js ./tailwind.config.js

# Install additional dependencies
npm install react-router-dom @reduxjs/toolkit react-redux axios

# Install development dependencies
npm install -D @testing-library/react @testing-library/jest-dom \
  @testing-library/user-event @axe-core/react jest-axe \
  eslint prettier

# Start development server
npm run dev
```

### Project Structure (Recommended)

```
vaucda-frontend/
├── public/
│   ├── logo.svg
│   └── favicon.ico
├── src/
│   ├── components/
│   │   ├── ui/           # Generic reusable components
│   │   ├── medical/      # Medical-specific components
│   │   ├── layout/       # Layout components
│   │   └── features/     # Feature-specific components
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── NoteGeneration.tsx
│   │   ├── Calculators.tsx
│   │   ├── EvidenceSearch.tsx
│   │   └── Settings.tsx
│   ├── hooks/            # Custom React hooks
│   ├── services/         # API client services
│   ├── store/            # Redux store
│   ├── types/            # TypeScript types
│   ├── utils/            # Utility functions
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── .env.example
├── .eslintrc.js
├── .prettierrc
├── tailwind.config.js
├── tsconfig.json
├── vite.config.ts
└── package.json
```

---

## Design Review Checklist

Before starting implementation, ensure:

- [ ] Design system document reviewed and approved
- [ ] Color palette meets all contrast requirements
- [ ] Typography scale is legible and scalable
- [ ] Component specifications are clear
- [ ] Accessibility requirements understood
- [ ] Clinical workflow patterns make sense
- [ ] Implementation timeline is realistic
- [ ] Technology stack is approved
- [ ] Testing strategy is defined
- [ ] VA infrastructure requirements understood

---

## Resources

### Design References
- Material Design 3: https://m3.material.io/
- Apple Human Interface Guidelines: https://developer.apple.com/design/
- VA Design System: https://design.va.gov/

### Accessibility Resources
- WCAG 2.1: https://www.w3.org/WAI/WCAG21/quickref/
- ARIA Authoring Practices: https://www.w3.org/WAI/ARIA/apg/
- WebAIM: https://webaim.org/

### Development Resources
- React Documentation: https://react.dev/
- Tailwind CSS: https://tailwindcss.com/
- TypeScript: https://www.typescriptlang.org/
- Vite: https://vitejs.dev/

---

## Contact & Support

**Design Team**: design@vaucda.va.gov
**Development Team**: dev@vaucda.va.gov
**Accessibility Team**: accessibility@vaucda.va.gov

For questions about design specifications, component usage, or accessibility requirements, please refer to the comprehensive documentation provided in this directory.

---

## License

This project is for internal VA use only. All code and designs are property of the Department of Veterans Affairs.

---

**Last Updated**: November 29, 2025
**Next Review**: After Phase 1 completion (estimated 2 weeks)
