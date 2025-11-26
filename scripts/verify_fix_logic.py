
def verify_logic(is_high_score, successes, issues):
    output = []
    
    if is_high_score:
        output.append("Successes & Strengths section shown")
        
        if successes:
            for success in successes:
                output.append(f"Success shown: {success}")
        elif not issues:
            output.append("No specific issues detected message shown")
            
    return output

def test_fix():
    # Case 1: High score, no successes, but has issues (The bug case)
    # Expected: "Successes & Strengths section shown" but NOT "No specific issues detected message shown"
    print("Testing Case 1: High score, no successes, has issues")
    result1 = verify_logic(is_high_score=True, successes=[], issues=['some_issue'])
    print(f"Result: {result1}")
    assert "Successes & Strengths section shown" in result1
    assert "No specific issues detected message shown" not in result1
    print("PASS")

    # Case 2: High score, no successes, no issues (The clean case)
    # Expected: Both messages shown
    print("\nTesting Case 2: High score, no successes, no issues")
    result2 = verify_logic(is_high_score=True, successes=[], issues=[])
    print(f"Result: {result2}")
    assert "Successes & Strengths section shown" in result2
    assert "No specific issues detected message shown" in result2
    print("PASS")

    # Case 3: High score, has successes (The ideal case)
    # Expected: Success shown, no "No specific issues detected"
    print("\nTesting Case 3: High score, has successes")
    result3 = verify_logic(is_high_score=True, successes=['Great job'], issues=[])
    print(f"Result: {result3}")
    assert "Success shown: Great job" in result3
    assert "No specific issues detected message shown" not in result3
    print("PASS")

if __name__ == "__main__":
    test_fix()
