# Calculator Input Schema - Quick Reference

**For:** Developers integrating with the Calculator Input Schema API
**Version:** 1.0
**Last Updated:** December 6, 2025

---

## API Endpoints

### Get Input Schema (Dedicated)
```http
GET /api/v1/calculators/{calculator_id}/input-schema
Authorization: Bearer {token}
```

**Response:**
```json
{
  "calculator_id": "capracalculator",
  "calculator_name": "CAPRA Score",
  "input_schema": [...]
}
```

---

### Get Calculator Info (Includes Schema)
```http
GET /api/v1/calculators/{calculator_id}
Authorization: Bearer {token}
```

**Response:**
```json
{
  "id": "capracalculator",
  "name": "CAPRA Score",
  "description": "...",
  "category": "prostate",
  "required_inputs": [...],
  "input_schema": [...]
}
```

---

## Schema Structure

### Field Metadata
Each field in `input_schema` array contains:

```json
{
  "field_name": "psa",              // Internal field identifier
  "display_name": "PSA",            // User-facing label
  "input_type": "numeric",          // Widget type: numeric, enum, boolean, text, date
  "required": true,                 // Is field mandatory?
  "description": "...",             // Full field description
  "unit": "ng/mL",                  // Measurement unit (optional)
  "min_value": 0.0,                 // Minimum value (numeric only)
  "max_value": 500.0,               // Maximum value (numeric only)
  "allowed_values": [1,2,3,4,5],    // Valid options (enum only)
  "default_value": null,            // Default value (optional)
  "example": "6.5",                 // Example value for placeholder
  "help_text": "..."                // Tooltip/help text
}
```

---

## Input Types

### Numeric
```json
{
  "input_type": "numeric",
  "min_value": 0.0,
  "max_value": 500.0,
  "unit": "ng/mL"
}
```
**Use:** `<input type="number" min="0" max="500" />`

---

### Enum
```json
{
  "input_type": "enum",
  "allowed_values": [1, 2, 3, 4, 5]
}
```
**Use:** `<select>` or `<radio>` with options from `allowed_values`

---

### Boolean
```json
{
  "input_type": "boolean"
}
```
**Use:** `<input type="checkbox" />` or toggle switch

---

### Text
```json
{
  "input_type": "text",
  "pattern": "^[0-9]{8}$"  // Optional regex
}
```
**Use:** `<input type="text" />`

---

### Date
```json
{
  "input_type": "date"
}
```
**Use:** `<input type="date" />` or date picker

---

## Frontend Integration Examples

### React Component

```typescript
interface InputSchemaField {
  field_name: string;
  display_name: string;
  input_type: 'numeric' | 'enum' | 'boolean' | 'text' | 'date';
  required: boolean;
  description: string;
  unit?: string;
  min_value?: number;
  max_value?: number;
  allowed_values?: any[];
  example?: string;
  help_text?: string;
}

function FormFieldFromSchema({ field }: { field: InputSchemaField }) {
  switch (field.input_type) {
    case 'numeric':
      return (
        <div>
          <label>{field.display_name} {field.required && '*'}</label>
          <input
            type="number"
            min={field.min_value}
            max={field.max_value}
            placeholder={field.example}
            required={field.required}
          />
          {field.unit && <span>{field.unit}</span>}
          <HelpTooltip text={field.help_text} />
        </div>
      );

    case 'enum':
      return (
        <div>
          <label>{field.display_name} {field.required && '*'}</label>
          <select required={field.required}>
            {field.allowed_values.map(value => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <HelpTooltip text={field.help_text} />
        </div>
      );

    // ... other types
  }
}
```

---

### Vue Component

```vue
<template>
  <div v-for="field in inputSchema" :key="field.field_name">
    <!-- Numeric Input -->
    <div v-if="field.input_type === 'numeric'" class="form-field">
      <label>
        {{ field.display_name }}
        <span v-if="field.required" class="required">*</span>
      </label>
      <input
        type="number"
        :min="field.min_value"
        :max="field.max_value"
        :placeholder="field.example"
        :required="field.required"
        v-model="formData[field.field_name]"
      />
      <span v-if="field.unit">{{ field.unit }}</span>
      <tooltip :text="field.help_text" />
    </div>

    <!-- Enum Input -->
    <div v-if="field.input_type === 'enum'" class="form-field">
      <label>
        {{ field.display_name }}
        <span v-if="field.required" class="required">*</span>
      </label>
      <select
        :required="field.required"
        v-model="formData[field.field_name]"
      >
        <option
          v-for="value in field.allowed_values"
          :key="value"
          :value="value"
        >
          {{ value }}
        </option>
      </select>
      <tooltip :text="field.help_text" />
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      inputSchema: [],
      formData: {}
    }
  },
  async mounted() {
    const response = await fetch(
      `/api/v1/calculators/${this.calculatorId}/input-schema`,
      { headers: { Authorization: `Bearer ${this.token}` }}
    );
    this.inputSchema = (await response.json()).input_schema;
  }
}
</script>
```

---

## Client-Side Validation

### JavaScript Validation Function

```javascript
function validateInput(field, value) {
  // Required field check
  if (field.required && (value === null || value === undefined || value === '')) {
    return { valid: false, error: `${field.display_name} is required` };
  }

  // Numeric validation
  if (field.input_type === 'numeric') {
    const numValue = parseFloat(value);

    if (isNaN(numValue)) {
      return { valid: false, error: `${field.display_name} must be a number` };
    }

    if (field.min_value !== null && numValue < field.min_value) {
      return {
        valid: false,
        error: `${field.display_name} must be at least ${field.min_value}`
      };
    }

    if (field.max_value !== null && numValue > field.max_value) {
      return {
        valid: false,
        error: `${field.display_name} must be at most ${field.max_value}`
      };
    }
  }

  // Enum validation
  if (field.input_type === 'enum') {
    if (!field.allowed_values.includes(value)) {
      return {
        valid: false,
        error: `${field.display_name} must be one of: ${field.allowed_values.join(', ')}`
      };
    }
  }

  return { valid: true };
}

// Validate entire form
function validateForm(schema, formData) {
  const errors = {};

  for (const field of schema) {
    const result = validateInput(field, formData[field.field_name]);
    if (!result.valid) {
      errors[field.field_name] = result.error;
    }
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors
  };
}
```

---

## TypeScript Interfaces

### Generate from Schema

```typescript
// For CAPRA calculator
interface CapraCalculatorInput {
  psa: number;  // 0-500
  gleason_primary: 1 | 2 | 3 | 4 | 5;
  gleason_secondary: 1 | 2 | 3 | 4 | 5;
  t_stage: "T1a" | "T1b" | "T1c" | "T2a" | "T2b" | "T2c" | "T3a" | "T3b";
  percent_positive_cores: number;  // 0-100
}

// Usage
const input: CapraCalculatorInput = {
  psa: 6.5,
  gleason_primary: 3,
  gleason_secondary: 4,
  t_stage: "T2a",
  percent_positive_cores: 40
};
```

---

## Common Use Cases

### 1. Build Form Automatically
```javascript
async function buildFormFromSchema(calculatorId) {
  const response = await fetch(`/api/v1/calculators/${calculatorId}/input-schema`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });

  const { input_schema } = await response.json();

  const form = document.createElement('form');

  for (const field of input_schema) {
    const fieldElement = createFieldElement(field);
    form.appendChild(fieldElement);
  }

  return form;
}
```

---

### 2. Pre-populate from Clinical Context
```javascript
async function prefillForm(calculatorId, clinicalData) {
  const response = await fetch(`/api/v1/calculators/${calculatorId}/input-schema`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });

  const { input_schema } = await response.json();
  const formData = {};

  for (const field of input_schema) {
    // Try to extract value from clinical context
    if (clinicalData[field.field_name]) {
      formData[field.field_name] = clinicalData[field.field_name];
    } else {
      formData[field.field_name] = field.default_value || '';
    }
  }

  return formData;
}
```

---

### 3. Generate Help Documentation
```javascript
async function generateFieldHelp(calculatorId) {
  const response = await fetch(`/api/v1/calculators/${calculatorId}/input-schema`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });

  const { input_schema } = await response.json();

  const helpDocs = input_schema.map(field => ({
    field: field.display_name,
    description: field.description,
    help: field.help_text,
    example: field.example,
    constraints: buildConstraintDescription(field)
  }));

  return helpDocs;
}

function buildConstraintDescription(field) {
  const parts = [];

  if (field.required) parts.push('Required');

  if (field.input_type === 'numeric') {
    parts.push(`Range: ${field.min_value}-${field.max_value}`);
    if (field.unit) parts.push(`Unit: ${field.unit}`);
  }

  if (field.input_type === 'enum') {
    parts.push(`Options: ${field.allowed_values.join(', ')}`);
  }

  return parts.join(' | ');
}
```

---

## Testing Your Integration

### Test Valid Input
```bash
curl -X POST http://localhost:8002/api/v1/calculators/capracalculator/calculate \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "psa": 6.5,
      "gleason_primary": 3,
      "gleason_secondary": 4,
      "t_stage": "T2a",
      "percent_positive_cores": 40.0
    }
  }'
```
**Expected:** HTTP 200 with calculator result

---

### Test Invalid Input
```bash
curl -X POST http://localhost:8002/api/v1/calculators/capracalculator/calculate \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "psa": 600,
      "gleason_primary": 3,
      "gleason_secondary": 4,
      "t_stage": "T2a",
      "percent_positive_cores": 40.0
    }
  }'
```
**Expected:** HTTP 400 with validation error

---

## Best Practices

### 1. Cache the Schema
```javascript
// Good: Cache schema to reduce API calls
const schemaCache = new Map();

async function getSchema(calculatorId) {
  if (!schemaCache.has(calculatorId)) {
    const response = await fetch(`/api/v1/calculators/${calculatorId}/input-schema`);
    const data = await response.json();
    schemaCache.set(calculatorId, data.input_schema);
  }
  return schemaCache.get(calculatorId);
}
```

---

### 2. Validate Client-Side First
```javascript
// Good: Validate before submitting
async function submitCalculator(calculatorId, inputs) {
  const schema = await getSchema(calculatorId);
  const validation = validateForm(schema, inputs);

  if (!validation.valid) {
    // Show errors to user
    displayErrors(validation.errors);
    return;
  }

  // Submit to server
  const response = await fetch(
    `/api/v1/calculators/${calculatorId}/calculate`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ inputs })
    }
  );

  // Handle response...
}
```

---

### 3. Use Help Text Effectively
```javascript
// Good: Show help text in tooltips and aria-labels
function createFieldWithHelp(field) {
  return `
    <div class="form-field">
      <label for="${field.field_name}">
        ${field.display_name}
        ${field.required ? '<span class="required">*</span>' : ''}
        <button
          type="button"
          class="help-button"
          aria-label="Help for ${field.display_name}"
          data-tooltip="${escapeHtml(field.help_text)}"
        >?</button>
      </label>
      <input
        id="${field.field_name}"
        name="${field.field_name}"
        aria-describedby="${field.field_name}-help"
      />
      <div id="${field.field_name}-help" class="help-text">
        ${field.description}
      </div>
    </div>
  `;
}
```

---

## Troubleshooting

### Schema Returns Empty Array
**Problem:** `input_schema: []`

**Cause:** Calculator hasn't implemented `get_input_schema()` yet

**Solution:** Contact backend team or use `required_inputs` list as fallback

---

### Authentication Fails
**Problem:** HTTP 403 "Not authenticated"

**Cause:** Missing or invalid token

**Solution:**
```javascript
// Ensure you're including the Authorization header
headers: {
  'Authorization': `Bearer ${token}`
}
```

---

### Validation Passes on Client but Fails on Server
**Problem:** Server returns HTTP 400 even though client validation passed

**Cause:** Server-side validation is more strict or has additional rules

**Solution:** Always handle server-side validation errors gracefully:
```javascript
try {
  const response = await submitCalculator(id, inputs);
  // Handle success
} catch (error) {
  if (error.status === 400) {
    // Show server validation errors to user
    displayServerErrors(error.details);
  }
}
```

---

## Support and Resources

### API Documentation
- Full API docs: (Check your organization's API portal)
- Swagger/OpenAPI: `http://localhost:8002/docs`

### Test Files
- Live API tests: `/home/gulab/PythonProjects/VAUCDA/backend/tests/test_live_schema_api.py`
- Full test report: `/home/gulab/PythonProjects/VAUCDA/backend/tests/reports/INPUT_SCHEMA_TEST_REPORT.md`

### Example Implementations
- CAPRA Calculator: `/home/gulab/PythonProjects/VAUCDA/backend/calculators/prostate/capra.py` (lines 55-112)

---

**Quick Reference Version:** 1.0
**Last Updated:** December 6, 2025
**Maintained By:** VAUCDA Development Team
