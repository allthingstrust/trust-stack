import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

def check_s3():
    bucket = os.getenv("SCREENSHOT_S3_BUCKET")
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    print(f"Checking S3 Configuration...")
    print(f"Bucket: {bucket}")
    print(f"AWS Access Key: {'*' * 16 + aws_access_key[-4:] if aws_access_key else 'NOT SET'}")
    print(f"AWS Secret: {'SET' if aws_secret else 'NOT SET'}")

    if not bucket:
        print("❌ DELETE_ME: SCREENSHOT_S3_BUCKET is not set in .env")
        return

    if not aws_access_key or not aws_secret:
        print("❌ AWS credentials are missing.")
        return

    try:
        s3 = boto3.client('s3', region_name=region)
        # Check bucket existence/access
        s3.head_bucket(Bucket=bucket)
        print(f"✅ Bucket '{bucket}' exists and is accessible.")
        
        # Test upload
        test_key = "test_write_access.txt"
        s3.put_object(Bucket=bucket, Key=test_key, Body=b"test")
        print(f"✅ Write access confirmed (uploaded {test_key}).")
        
        # Cleanup
        s3.delete_object(Bucket=bucket, Key=test_key)
        print(f"✅ Cleanup successful.")
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"❌ S3 Error: {error_code} - {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")

if __name__ == "__main__":
    check_s3()
