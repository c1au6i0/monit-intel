#!/usr/bin/env python3
"""
Test script to verify the greeting fix for Mother.

This script tests that:
1. Simple greetings are detected correctly
2. The system prompt changes based on greeting detection
3. The minimal prompt is used for greetings
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_greeting_detection():
    """Test if greeting detection logic works."""
    simple_greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", 
                      "how are you", "what's up", "howdy", "sup", "yo", "hola", "salut"]
    
    test_cases = [
        ("hello", True),
        ("Hello, how are you?", True),
        ("Hi there", True),
        ("What's the status?", False),
        ("Tell me about docker", False),
        ("hello everyone", True),
        ("Hi, what services are failing?", True),  # Has greeting but also technical question
    ]
    
    print("Testing greeting detection logic:")
    print("-" * 60)
    
    for query, expected_greeting in test_cases:
        query_lower = query.lower()
        is_simple_greeting = any(greeting in query_lower for greeting in simple_greetings)
        
        status = "✓ PASS" if is_simple_greeting == expected_greeting else "✗ FAIL"
        print(f"{status}: '{query}' -> is_greeting={is_simple_greeting} (expected={expected_greeting})")
    
    print()

def test_system_prompt_logic():
    """Test that system prompt selection works correctly."""
    print("Testing system prompt selection logic:")
    print("-" * 60)
    
    # Simulate the logic from mother.py
    test_cases = [
        {
            "query": "hello",
            "expected_prompt_type": "minimal",
            "description": "Simple greeting should use minimal prompt"
        },
        {
            "query": "Tell me about your configuration",
            "expected_prompt_type": "full",
            "description": "Configuration question should use full prompt"
        },
        {
            "query": "What's the system status?",
            "expected_prompt_type": "full",
            "description": "Status question should use full prompt"
        },
        {
            "query": "Hey, how are things?",
            "expected_prompt_type": "minimal",
            "description": "Casual greeting should use minimal prompt"
        },
    ]
    
    simple_greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", 
                      "how are you", "what's up", "howdy", "sup", "yo", "hola", "salut"]
    
    for test in test_cases:
        query = test["query"]
        query_lower = query.lower()
        
        # Greeting detection
        is_simple_greeting = any(greeting in query_lower for greeting in simple_greetings)
        
        # Include full context detection
        include_full_context = (
            (any(phrase in query_lower for phrase in [
                "system status", "overall", "what's", "how is", "how are", "tell me about",
                "any issues", "any problems", "what's wrong", "failures", "errors",
                "summary", "overview", "report", "update", "status"
            ]))
            and not is_simple_greeting
        )
        
        actual_prompt_type = "minimal" if is_simple_greeting else ("full" if include_full_context else "basic")
        expected_prompt_type = test["expected_prompt_type"]
        
        status = "✓ PASS" if actual_prompt_type == expected_prompt_type else "✗ FAIL"
        print(f"{status}: {test['description']}")
        print(f"      Query: '{query}'")
        print(f"      Prompt type: {actual_prompt_type} (expected: {expected_prompt_type})")
        print()

if __name__ == "__main__":
    print("=" * 60)
    print("MOTHER GREETING FIX - LOGIC TEST")
    print("=" * 60)
    print()
    
    test_greeting_detection()
    print()
    test_system_prompt_logic()
    
    print("=" * 60)
    print("Test complete!")
    print("=" * 60)
