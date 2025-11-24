#!/usr/bin/env python3
"""
Test script to verify text extraction spacing fix.

This test reproduces the Reebok spacing issue where a <br> tag
was causing text to be concatenated without proper spacing.
"""

from bs4 import BeautifulSoup


def test_br_tag_spacing():
    """Test that <br> tags are properly converted to spaces."""
    html = """
    <h2 class="title">
        Subscribe to our news alerts
        <br class="d-none d-lg-block">
        and stay informed.
    </h2>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    h2 = soup.find('h2')
    
    # Old way (without separator) - would produce "alertsand"
    text_without_separator = h2.get_text(strip=True)
    print(f"Without separator: '{text_without_separator}'")
    
    # New way (with separator) - should produce "alerts and"
    text_with_separator = h2.get_text(separator=" ", strip=True)
    print(f"With separator: '{text_with_separator}'")
    
    # Verify the fix
    assert "alertsand" not in text_with_separator, "Text should not have concatenated words"
    assert "alerts and" in text_with_separator, "Text should have proper spacing"
    print("✓ BR tag spacing test passed!")


def test_nested_divs_spacing():
    """Test that nested divs are properly converted to spaces."""
    html = """
    <div class="container">
        <div class="item">First item</div>
        <div class="item">Second item</div>
    </div>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_='container')
    
    text_with_separator = container.get_text(separator=" ", strip=True)
    print(f"Nested divs: '{text_with_separator}'")
    
    assert "First item Second item" in text_with_separator or "First item  Second item" in text_with_separator
    print("✓ Nested divs spacing test passed!")


def test_paragraph_spacing():
    """Test that paragraph tags are properly converted to spaces."""
    html = """
    <div>
        <p>First paragraph</p>
        <p>Second paragraph</p>
    </div>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    div = soup.find('div')
    
    text_with_separator = div.get_text(separator=" ", strip=True)
    print(f"Paragraphs: '{text_with_separator}'")
    
    assert "First paragraph Second paragraph" in text_with_separator or "First paragraph  Second paragraph" in text_with_separator
    print("✓ Paragraph spacing test passed!")


def test_list_item_spacing():
    """Test that list items with inline elements are properly spaced."""
    html = """
    <li>
        <strong>Product Name</strong>
        <br>
        <span class="price">$99.99</span>
    </li>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    li = soup.find('li')
    
    text_with_separator = li.get_text(separator=" ", strip=True)
    print(f"List item: '{text_with_separator}'")
    
    assert "Product Name $99.99" in text_with_separator or "Product Name  $99.99" in text_with_separator
    assert "Name$99.99" not in text_with_separator, "Should not have concatenated text"
    print("✓ List item spacing test passed!")


def test_table_cell_spacing():
    """Test that table cells with inline elements are properly spaced."""
    html = """
    <td>
        <span>Cell</span>
        <br>
        <span>Content</span>
    </td>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    td = soup.find('td')
    
    text_with_separator = td.get_text(separator=" ", strip=True)
    print(f"Table cell: '{text_with_separator}'")
    
    assert "Cell Content" in text_with_separator or "Cell  Content" in text_with_separator
    assert "CellContent" not in text_with_separator, "Should not have concatenated text"
    print("✓ Table cell spacing test passed!")


if __name__ == "__main__":
    print("Testing text extraction spacing fixes...\n")
    
    test_br_tag_spacing()
    print()
    test_nested_divs_spacing()
    print()
    test_paragraph_spacing()
    print()
    test_list_item_spacing()
    print()
    test_table_cell_spacing()
    
    print("\n✅ All text extraction spacing tests passed!")
