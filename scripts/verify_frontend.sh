#!/bin/bash

# VAUCDA Frontend Verification Script
# Verifies all frontend files are in place and ready for development

set -e

echo "========================================"
echo "VAUCDA Frontend Verification"
echo "========================================"
echo ""

FRONTEND_DIR="/home/gulab/PythonProjects/VAUCDA/frontend"
ERRORS=0

# Function to check if file exists
check_file() {
    if [ -f "$1" ]; then
        echo "✓ $2"
    else
        echo "✗ $2 - MISSING"
        ERRORS=$((ERRORS + 1))
    fi
}

# Function to check if directory exists
check_dir() {
    if [ -d "$1" ]; then
        echo "✓ $2"
    else
        echo "✗ $2 - MISSING"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "Checking Configuration Files..."
check_file "$FRONTEND_DIR/package.json" "package.json"
check_file "$FRONTEND_DIR/tsconfig.json" "tsconfig.json"
check_file "$FRONTEND_DIR/vite.config.ts" "vite.config.ts"
check_file "$FRONTEND_DIR/tailwind.config.js" "tailwind.config.js"
check_file "$FRONTEND_DIR/.env.example" ".env.example"
echo ""

echo "Checking Directory Structure..."
check_dir "$FRONTEND_DIR/src/api" "src/api"
check_dir "$FRONTEND_DIR/src/components" "src/components"
check_dir "$FRONTEND_DIR/src/pages" "src/pages"
check_dir "$FRONTEND_DIR/src/store" "src/store"
check_dir "$FRONTEND_DIR/src/hooks" "src/hooks"
check_dir "$FRONTEND_DIR/src/types" "src/types"
check_dir "$FRONTEND_DIR/src/utils" "src/utils"
echo ""

echo "Checking API Files..."
check_file "$FRONTEND_DIR/src/api/client.ts" "api/client.ts"
check_file "$FRONTEND_DIR/src/api/auth.ts" "api/auth.ts"
check_file "$FRONTEND_DIR/src/api/notes.ts" "api/notes.ts"
check_file "$FRONTEND_DIR/src/api/calculators.ts" "api/calculators.ts"
echo ""

echo "Checking Redux Store..."
check_file "$FRONTEND_DIR/src/store/index.ts" "store/index.ts"
check_file "$FRONTEND_DIR/src/store/slices/authSlice.ts" "store/slices/authSlice.ts"
check_file "$FRONTEND_DIR/src/store/slices/noteSlice.ts" "store/slices/noteSlice.ts"
check_file "$FRONTEND_DIR/src/store/slices/calculatorSlice.ts" "store/slices/calculatorSlice.ts"
echo ""

echo "Checking Components..."
check_file "$FRONTEND_DIR/src/components/common/Button.tsx" "components/common/Button.tsx"
check_file "$FRONTEND_DIR/src/components/common/Input.tsx" "components/common/Input.tsx"
check_file "$FRONTEND_DIR/src/components/common/Card.tsx" "components/common/Card.tsx"
check_file "$FRONTEND_DIR/src/components/layout/Header.tsx" "components/layout/Header.tsx"
check_file "$FRONTEND_DIR/src/components/layout/Sidebar.tsx" "components/layout/Sidebar.tsx"
echo ""

echo "Checking Pages..."
check_file "$FRONTEND_DIR/src/pages/Login.tsx" "pages/Login.tsx"
check_file "$FRONTEND_DIR/src/pages/Dashboard.tsx" "pages/Dashboard.tsx"
check_file "$FRONTEND_DIR/src/pages/NoteGeneration.tsx" "pages/NoteGeneration.tsx"
echo ""

echo "Checking Root Files..."
check_file "$FRONTEND_DIR/src/App.tsx" "src/App.tsx"
check_file "$FRONTEND_DIR/src/main.tsx" "src/main.tsx"
check_file "$FRONTEND_DIR/index.html" "index.html"
echo ""

echo "Counting Files..."
TS_FILES=$(find "$FRONTEND_DIR/src" -name "*.ts" -o -name "*.tsx" 2>/dev/null | wc -l)
echo "TypeScript files: $TS_FILES"

TOTAL_FILES=$(find "$FRONTEND_DIR" -type f ! -path "*/node_modules/*" ! -path "*/.git/*" 2>/dev/null | wc -l)
echo "Total files: $TOTAL_FILES"
echo ""

echo "Checking Dependencies..."
if [ -f "$FRONTEND_DIR/package.json" ]; then
    if [ -d "$FRONTEND_DIR/node_modules" ]; then
        echo "✓ node_modules directory exists"
    else
        echo "✗ node_modules not found - Run 'npm install'"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "✗ package.json missing"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo "Checking Environment Configuration..."
if [ -f "$FRONTEND_DIR/.env" ]; then
    echo "✓ .env file exists"
else
    echo "⚠ .env file not found - Copy from .env.example"
fi
echo ""

echo "========================================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed!"
    echo ""
    echo "Frontend is ready for development."
    echo ""
    echo "Next steps:"
    echo "1. cd $FRONTEND_DIR"
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo "2. npm install"
        echo "3. npm run dev"
    else
        echo "2. npm run dev"
    fi
    echo ""
    echo "Application will be available at http://localhost:3000"
else
    echo "❌ Found $ERRORS error(s)"
    echo ""
    echo "Please fix the issues above before proceeding."
fi
echo "========================================"
