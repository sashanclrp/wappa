#!/usr/bin/env python3
"""
Test script to verify app.run() works properly.
"""

from wappa import Wappa, WappaEventHandler
from example_webhook_usage import MyEventHandler

def main():
    print("🧪 Testing app.run() method...")
    
    app = Wappa()
    handler = MyEventHandler()
    app.set_event_handler(handler)
    
    print("🚀 Starting server with app.run()...")
    print("💡 Press CTRL+C to stop")
    print("🔗 Test: curl http://localhost:8000/health")
    print()
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()