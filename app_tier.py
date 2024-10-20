import boto3
import json
import base64
import io
import time
import face_recognition  # Make sure this is accessible as a module

# S3 Bucket Names
ASU_ID = '1229850390'  # Replace with your ASU ID
input_bucket_name = f'{ASU_ID}-in-bucket'
output_bucket_name = f'{ASU_ID}-out-bucket'

# SQS Queue URLs
sqs = boto3.client('sqs', region_name='us-east-1')
request_queue_url = 'https://sqs.us-west-2.amazonaws.com/442042549532/1229850390-req-queue'
response_queue_url = 'https://sqs.us-west-2.amazonaws.com/442042549532/1229850390-resp-queue'

# Initialize S3 client
s3 = boto3.client('s3')

def upload_image_to_s3(bucket_name, file_name, image_data):
    """
    Uploads the original image to the specified S3 input bucket.
    """
    decoded_image = base64.b64decode(image_data)
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=decoded_image)
    print(f"Uploaded {file_name} to S3 input bucket {bucket_name}")

def upload_classification_to_s3(bucket_name, file_name, classification_result):
    """
    Uploads the classification result to the specified S3 bucket.
    """
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=classification_result)

def process_image(image_data, image_name):
    """
    This function takes in base64-encoded image data, processes it, and returns the
    face recognition result using the face_match function from face_recognition.py.
    """
    # Decode the base64 image data
    img_path = f'/tmp/{image_name}'  # Temp path for processing
    with open(img_path, 'wb') as f:
        f.write(base64.b64decode(image_data))

    # Perform face recognition using the model and return the result
    return face_recognition.face_match(img_path, 'data.pt')

def poll_sqs():
    """
    Poll the SQS request queue for image processing jobs and send the results
    back to the response queue.
    """
    while True:
        response = sqs.receive_message(
            QueueUrl=request_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20  # Enable long polling
        )

        if 'Messages' in response:
            for message in response['Messages']:
                receipt_handle = message['ReceiptHandle']
                body = json.loads(message['Body'])
                file_name = body['fileName']
                file_content = body['fileContent']  # Base64-encoded image content

                print(f"Processing image: {file_name}")
                person_name, confidence = process_image(file_content, file_name)

                # Upload the classification result to S3 output bucket
                classification_result = f"{person_name}"
                upload_classification_to_s3(output_bucket_name, file_name.split('.')[0], classification_result)

                # Send the result to the Response Queue
                sqs.send_message(
                    QueueUrl=response_queue_url,
                    MessageBody=json.dumps({'fileName': file_name, 'classificationResult': person_name})
                )

                # Delete the processed message from the Request Queue
                sqs.delete_message(QueueUrl=request_queue_url, ReceiptHandle=receipt_handle)

                print(f"Processed {file_name}: {person_name}")
        else:
            print("No messages in the queue. Waiting...")
            time.sleep(5)

if __name__ == "__main__":
    print("Starting the App Tier instance...")
    poll_sqs()  # This handles message processing from SQS
