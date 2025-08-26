#!/bin/bash

echo "🔧 Fixing missing get_logger imports..."

# List of files that need the import
files_needing_import=(
    "wappa/schemas/factory.py"
    "wappa/processors/factory.py"
    "wappa/processors/base_processor.py"
    "wappa/messaging/whatsapp/handlers/whatsapp_template_handler.py"
    "wappa/messaging/whatsapp/handlers/whatsapp_interactive_handler.py"
    "wappa/messaging/whatsapp/handlers/whatsapp_media_handler.py"
    "wappa/messaging/whatsapp/handlers/whatsapp_specialized_handler.py"
    "wappa/messaging/whatsapp/messenger/whatsapp_messenger.py"
    "wappa/messaging/whatsapp/client/whatsapp_client.py"
    "wappa/webhooks/factory.py"
    "wappa/core/events/default_handlers.py"
    "wappa/core/events/event_dispatcher.py"
    "wappa/api/routes/whatsapp/whatsapp_messages.py"
    "wappa/api/routes/webhooks.py"
    "wappa/api/middleware/error_handler.py"
    "wappa/api/middleware/request_logging.py"
    "wappa/api/middleware/tenant.py"
    "wappa/api/dependencies/whatsapp_dependencies.py"
)

for file in "${files_needing_import[@]}"; do
    if [ -f "$file" ]; then
        # Check if file uses get_logger but doesn't have the import
        if grep -q "get_logger(" "$file" && ! grep -q "from wappa.core.logging.logger import get_logger" "$file"; then
            echo "  ✓ Adding import to $file"
            
            # Find the last import line
            last_import_line=$(grep -n "^from\|^import" "$file" | tail -n1 | cut -d: -f1)
            
            if [ -n "$last_import_line" ]; then
                # Insert after the last import
                sed -i "${last_import_line}a\\
from wappa.core.logging.logger import get_logger" "$file"
            else
                # If no imports found, add after docstring or at beginning
                docstring_end=$(grep -n '"""' "$file" | head -n2 | tail -n1 | cut -d: -f1)
                if [ -n "$docstring_end" ]; then
                    sed -i "${docstring_end}a\\
\\
from wappa.core.logging.logger import get_logger" "$file"
                else
                    # Add at the beginning after first comment block
                    sed -i '1a\\
from wappa.core.logging.logger import get_logger' "$file"
                fi
            fi
        fi
    fi
done

echo "✅ Import fixes completed!"

# Verify the fixes
echo ""
echo "🔍 Final verification:"
missing_imports=0
for file in "${files_needing_import[@]}"; do
    if [ -f "$file" ]; then
        if grep -q "get_logger(" "$file" && ! grep -q "from wappa.core.logging.logger import get_logger" "$file"; then
            echo "⚠️  $file still missing import"
            ((missing_imports++))
        fi
    fi
done

if [ "$missing_imports" -eq 0 ]; then
    echo "✅ All files now have proper imports!"
else
    echo "⚠️  $missing_imports files still need imports"
fi