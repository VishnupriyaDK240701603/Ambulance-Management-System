#!/usr/bin/env python3
"""LifeLine Dispatch — 3D Emergency Response Simulator
Entry point script.
"""
import os
import sys

# Add workspace directory to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app.application import LifeLineDispatchApp


def main():
    headless = "--headless" in sys.argv
    app = LifeLineDispatchApp(headless=headless)
    app.run()

if __name__ == "__main__":
    main()
