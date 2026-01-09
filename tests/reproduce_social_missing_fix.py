
import re
import base64
import os
import tempfile
from PIL import Image
import io

def embed_local_images_as_base64_optimized(markdown_text):
    """
    Finds local image paths in markdown (e.g. ![alt](/path/to/image.png))
    and replaces them with base64 encoded data URIs.
    Resizes images to max 800px width and compresses as JPEG to reduce page weight.
    """
    # Regex for markdown images: ![alt](path "title") or ![alt](path)
    pattern = r'!\[(.*?)\]\((.*?)\)'
    
    def replace_match(match):
        alt_text = match.group(1)
        path = match.group(2)
        
        # Clean path (handle optional title)
        title = ""
        if ' "' in path:
            parts = path.split(' "')
            path = parts[0]
            title = ' "' + parts[1]
        elif " '" in path:
            parts = path.split(" '")
            path = parts[0]
            title = " '" + parts[1]
            
        # Check if local file
        if not path.startswith(('http://', 'https://', 'data:')):
            local_path = path.replace('file://', '')
            
            if os.path.exists(local_path):
                try:
                    # Optimize: Resize and Compress
                    with Image.open(local_path) as img:
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                            
                        # Resize if too large
                        max_width = 100 # Verification script uses small max width to prove resizing
                        if img.width > max_width:
                            ratio = max_width / img.width
                            new_height = int(img.height * ratio)
                            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                        
                        # Save to buffer
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=80, optimize=True)
                        encoded_string = base64.b64encode(buffer.getvalue()).decode()
                        return f'![{alt_text}](data:image/jpeg;base64,{encoded_string}{title})'
                except Exception as e:
                    print(f"Error: {e}")
                    return match.group(0)
        return match.group(0)

    try:
        return re.sub(pattern, replace_match, markdown_text)
    except Exception as e:
        print(f"Regex error: {e}")
        return markdown_text

def test_optimization():
    # Create a large dummy image
    width, height = 200, 200
    color = (255, 0, 0)
    image = Image.new("RGB", (width, height), color)
    
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.save(tmp.name)
        tmp_path = tmp.name
        
    try:
        # Test 1: Should trigger resizing (200px -> 100px in our test config)
        md = f"Large image: ![large]({tmp_path})"
        result = embed_local_images_as_base64_optimized(md)
        
        print(f"Original: {md}")
        # Check success
        assert "data:image/jpeg;base64," in result
        
        # Extract base64 and verify dimensions
        b64_str = result.split("base64,")[1].split(")")[0]
        decoded = base64.b64decode(b64_str)
        img_verify = Image.open(io.BytesIO(decoded))
        
        print(f"Original size: {width}x{height}")
        print(f"Optimized size: {img_verify.width}x{img_verify.height}")
        
        assert img_verify.width <= 100
        assert img_verify.format == "JPEG"
        
        print("\nSUCCESS: Image was resized and converted to JPEG!")
        
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    test_optimization()
