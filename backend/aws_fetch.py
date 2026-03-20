from datetime import datetime, timedelta, timezone
import os
import random

from aws_session import get_boto3_session, is_aws_configured, use_simulation_mode


def _extract_instance_name(tags):
    if not tags:
        return "Unnamed"
    for tag in tags:
        if tag.get("Key") == "Name" and tag.get("Value"):
            return tag["Value"]
    return "Unnamed"


# function to get my instances from AWS or make fake ones
def get_ec2_instances():
    if use_simulation_mode():
        return [
            {"id": "i-1234567890abcdef0", "type": "t2.micro", "name": "Web Server"},
            {"id": "i-1234567890abcdef1", "type": "t2.small", "name": "Database"},
            {"id": "i-1234567890abcdef2", "type": "t3.micro", "name": "App Server"},
        ]

    if is_aws_configured():
        try:
            session = get_boto3_session()
            ec2 = session.client("ec2")
            
            # find running servers
            response = ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            instances = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instances.append({
                        "id": instance['InstanceId'],
                        "type": instance['InstanceType'],
                        "name": _extract_instance_name(instance.get("Tags"))
                    })
            return instances
        except Exception as e:
            print(f"AWS Error: {e}")

    return []


# function to get cpu memory
def get_cpu_utilization(instance_id):
    if use_simulation_mode():
        return random.uniform(5, 95)

    if is_aws_configured():
        try:
            session = get_boto3_session()
            cloudwatch = session.client("cloudwatch")

            # Use a recent window so CloudWatch has datapoints.
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=6)
            
            # ask for cpu
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                Period=300,
                StartTime=start_time,
                EndTime=end_time,
                Statistics=['Average']
            )
            
            if response['Datapoints']:
                latest = sorted(response["Datapoints"], key=lambda d: d.get("Timestamp", end_time))[-1]
                return float(latest.get("Average", 0.0))
        except Exception as e:
            print(f"CloudWatch Error: {e}")

    return 0.0
