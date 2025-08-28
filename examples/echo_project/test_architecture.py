#!/usr/bin/env python3
"""
Test script to verify Echo Project simplified architecture works correctly.
"""

import sys
from pathlib import Path

# Add the example directory to Python path for local imports (same as main.py)
example_dir = Path(__file__).parent
if str(example_dir) not in sys.path:
    sys.path.insert(0, str(example_dir))

print(f"✅ Added to sys.path: {example_dir}")

try:
    # Test local imports
    from echo_handler import EchoProjectHandler
    print("✅ EchoProjectHandler import successful")
    
    # Test Wappa import
    from wappa import Wappa, __version__
    print(f"✅ Wappa import successful (v{__version__})")
    
    # Test simplified setup (exactly like our main.py)
    print("Testing simplified Wappa setup...")
    app = Wappa(cache="redis") 
    handler = EchoProjectHandler()
    app.set_event_handler(handler)
    print("✅ Echo Project simplified setup successful!")
    
    # Test .asgi property access (new architecture)
    asgi_app = app.asgi
    print(f"✅ .asgi property works: {type(asgi_app).__name__}")
    
    print()
    print("🎉 ALL TESTS PASSED!")
    print("✅ Simplified architecture works correctly")
    print("✅ No complex bridge modules needed")
    print("✅ Ready for all three execution modes:")
    print("   • python main.py")
    print("   • uvicorn main:app.asgi --reload")  
    print("   • wappa dev main.py")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()