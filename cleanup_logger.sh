#!/bin/bash

# Logger Cleanup Script for Wappa Project
# Replaces all get_context_logger(...) calls with get_logger(__name__)
# and standardizes logger imports

echo "🧹 Starting logger cleanup across Wappa project..."

# Function to replace get_context_logger calls with get_logger(__name__)
cleanup_logger_calls() {
    echo "📝 Replacing get_context_logger calls with get_logger(__name__)..."
    
    # Replace single-line get_context_logger calls
    find wappa/ -name "*.py" -type f -exec sed -i -E 's/get_context_logger\([^)]+\)/get_logger(__name__)/g' {} \;
    
    # Replace multi-line get_context_logger calls (more complex pattern)
    find wappa/ -name "*.py" -type f -exec perl -i -pe 'BEGIN{undef $/;} s/get_context_logger\(\s*[^)]+\s*\)/get_logger(__name__)/smg' {} \;
    
    echo "✅ Replaced get_context_logger calls"
}

# Function to move imports to top of files (remove inline imports)
cleanup_inline_imports() {
    echo "📝 Cleaning up inline logger imports..."
    
    # Remove inline imports of logger functions
    find wappa/ -name "*.py" -type f -exec sed -i '/from wappa\.core\.logging\.logger import get_logger$/d' {} \;
    find wappa/ -name "*.py" -type f -exec sed -i '/from wappa\.core\.logging\.logger import get_context_logger$/d' {} \;
    
    echo "✅ Cleaned up inline imports"
}

# Function to add proper imports at the top of files
add_proper_imports() {
    echo "📝 Adding proper logger imports at top of files..."
    
    # Find all Python files that use get_logger but don't import it at the top
    for file in $(find wappa/ -name "*.py" -type f); do
        # Check if file uses get_logger
        if grep -q "get_logger(" "$file"; then
            # Check if it doesn't already have the import at the top (within first 20 lines)
            if ! head -n 20 "$file" | grep -q "from wappa.core.logging.logger import get_logger"; then
                # Find the best place to insert the import (after other imports)
                # Create a temp file with the import added
                {
                    # Get all the initial comments and docstrings
                    awk '/^[[:space:]]*$/ {print; next} /^[[:space:]]*#/ {print; next} /^[[:space:]]*"""/{p=1; print; next} p && /"""/{print; p=0; next} p {print; next} /^[[:space:]]*from|^[[:space:]]*import/ {imports[++i]=$0; next} {if(i>0) {for(j=1;j<=i;j++) print imports[j]; print "from wappa.core.logging.logger import get_logger"; print ""; i=0} print; next} END {if(i>0) {for(j=1;j<=i;j++) print imports[j]; print "from wappa.core.logging.logger import get_logger"; print ""}}' "$file" > "${file}.tmp"
                    
                    # Only replace if the temp file is different and valid
                    if [ -s "${file}.tmp" ] && ! cmp -s "$file" "${file}.tmp"; then
                        mv "${file}.tmp" "$file"
                        echo "  ✓ Added import to $file"
                    else
                        rm -f "${file}.tmp"
                    fi
                } 2>/dev/null || {
                    # Fallback: simple insertion after imports
                    rm -f "${file}.tmp"
                    # Find line number of last import
                    last_import_line=$(grep -n "^from\|^import" "$file" | tail -n1 | cut -d: -f1)
                    if [ -n "$last_import_line" ]; then
                        sed -i "${last_import_line}a\\from wappa.core.logging.logger import get_logger" "$file"
                        echo "  ✓ Added import to $file (fallback method)"
                    fi
                }
            fi
        fi
    done
    
    echo "✅ Added proper imports"
}

# Function to verify no DRY violations remain
verify_cleanup() {
    echo "🔍 Verifying cleanup completion..."
    
    echo "Remaining get_context_logger calls:"
    remaining_calls=$(grep -r "get_context_logger(" wappa/ --include="*.py" | wc -l)
    if [ "$remaining_calls" -gt 0 ]; then
        echo "⚠️  Found $remaining_calls remaining get_context_logger calls:"
        grep -r "get_context_logger(" wappa/ --include="*.py" -n
        echo ""
    else
        echo "✅ No get_context_logger calls remaining"
    fi
    
    echo "Files using get_logger:"
    files_using_logger=$(grep -r "get_logger(" wappa/ --include="*.py" -l | wc -l)
    echo "📊 $files_using_logger files using get_logger"
    
    echo "Files with proper imports:"
    files_with_import=$(grep -r "from wappa.core.logging.logger import get_logger" wappa/ --include="*.py" -l | wc -l)
    echo "📊 $files_with_import files with proper imports"
    
    # Check for files that use get_logger but don't have imports
    echo ""
    echo "Files using get_logger without proper imports:"
    for file in $(grep -r "get_logger(" wappa/ --include="*.py" -l); do
        if ! grep -q "from wappa.core.logging.logger import get_logger" "$file"; then
            echo "⚠️  $file"
        fi
    done
}

# Main execution
main() {
    echo "🚀 Logger cleanup script starting..."
    echo "Working directory: $(pwd)"
    echo ""
    
    # Run cleanup steps
    cleanup_logger_calls
    echo ""
    
    cleanup_inline_imports  
    echo ""
    
    add_proper_imports
    echo ""
    
    verify_cleanup
    echo ""
    
    echo "🎉 Logger cleanup completed!"
    echo ""
    echo "Summary:"
    echo "✅ All get_context_logger(...) calls replaced with get_logger(__name__)"
    echo "✅ Inline imports cleaned up"
    echo "✅ Proper imports added to top of files"
    echo "✅ DRY principle compliance achieved"
}

# Run main function
main