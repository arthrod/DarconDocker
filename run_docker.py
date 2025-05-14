#!/usr/bin/env python
"""
Simple script to build and run Archon Docker containers.
"""

import os
import sys
import subprocess
import time
import platform
import requests
from dotenv import load_dotenv
from pathlib import Path

def run_command(command, cwd=None):
    """Run a command and print output in real-time."""
    print(f"Running: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,  
        cwd=cwd
    )
    
    for line in process.stdout:
        try:
            decoded_line = line.decode('utf-8', errors='replace')
            print(decoded_line.strip())
        except Exception as e:
            print(f"Error processing output: {e}")
    
    process.wait()
    return process.returncode

def check_docker():
    """Check if Docker is installed and running."""
    try:
        subprocess.run(
            ["docker", "--version"], 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("Error: Docker is not installed or not in PATH")
        return False

def remove_container_if_exists(container_name):
    """Check if container exists and remove it if it does."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "--filter", f"name={container_name}"],
            check=True,
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print(f"\n=== Removing existing {container_name} container ===")
            container_id = result.stdout.strip()
            print(f"Found container with ID: {container_id}")
            
            # Check if the container is running
            running_check = subprocess.run(
                ["docker", "ps", "-q", "--filter", "id=" + container_id],
                check=True,
                capture_output=True,
                text=True
            )
            
            # If running, stop it first
            if running_check.stdout.strip():
                print("Container is running. Stopping it first...")
                stop_result = run_command(["docker", "stop", container_id])
                if stop_result != 0:
                    print("Warning: Failed to stop container gracefully, will try force removal")
            
            # Remove the container with force flag to ensure it's removed
            print("Removing container...")
            rm_result = run_command(["docker", "rm", "-f", container_id])
            if rm_result != 0:
                print(f"Error: Failed to remove container. Please remove it manually with:")
                print(f"  docker rm -f {container_id}")
                return False
            
            print("Container successfully removed")
        return True
    except subprocess.SubprocessError as e:
        print(f"Error checking for existing containers: {e}")
        return False

def main():
    """Main function to build and run Archon containers."""
    # Check if Docker is available
    if not check_docker():
        return 1
    
    # Get the base directory
    base_dir = Path(__file__).parent.absolute()
    
    # Check for .env file
    env_file = base_dir / ".env"
    env_args = []
    if env_file.exists():
        print(f"Using environment file: {env_file}")
        env_args = ["--env-file", str(env_file)]
    else:
        print("No .env file found. Continuing without environment variables.")
    
    # Build the main darchon-docker-mcp container
    print("\n=== Building main darchon-docker-mcp container ===")
    if run_command(["docker", "build", "-t", "darchon-docker-mcp:latest", "."], cwd=base_dir) != 0:
        print("Error building main darchon-docker-mcp container")
        return 1
    
    # Check if the container exists (running or stopped)
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "--filter", "name=darchon-docker-mcp"],
            check=True,
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print("\n=== Removing existing Archon container ===")
            container_id = result.stdout.strip()
            print(f"Found container with ID: {container_id}")
            
            # Check if the container is running
            running_check = subprocess.run(
                ["docker", "ps", "-q", "--filter", "id=" + container_id],
                check=True,
                capture_output=True,
                text=True
            )
            
            # If running, stop it first
            if running_check.stdout.strip():
                print("Container is running. Stopping it first...")
                stop_result = run_command(["docker", "stop", container_id])
                if stop_result != 0:
                    print("Warning: Failed to stop container gracefully, will try force removal")
            
            # Remove the container with force flag to ensure it's removed
            print("Removing container...")
            rm_result = run_command(["docker", "rm", "-f", container_id])
            if rm_result != 0:
                print("Error: Failed to remove container. Please remove it manually with:")
                print(f"  docker rm -f {container_id}")
                return 1
            
            print("Container successfully removed")
    except subprocess.SubprocessError as e:
        print(f"Error checking for existing containers: {e}")
        pass
    
    # Check if networks exist and create if needed
    try:
        # Check archon-network
        network_result = subprocess.run(
            ["docker", "network", "inspect", "archon-network"],
            check=False,
            capture_output=True
        )
        if network_result.returncode != 0:
            print("\n=== Creating archon-network ===")
            if run_command(["docker", "network", "create", "archon-network"]) != 0:
                print("Error creating archon-network")
                return 1
        else:
            print("\n=== Using existing archon-network ===")
            
        # Check supabase_default network
        network_result = subprocess.run(
            ["docker", "network", "inspect", "supabase_default"],
            check=False,
            capture_output=True
        )
        if network_result.returncode != 0:
            print("\n=== Supabase network not found, will create it ===")
            if run_command(["docker", "network", "create", "supabase_default"]) != 0:
                print("Error creating supabase_default network")
                return 1
        else:
            print("\n=== Using existing supabase_default network ===")
    except Exception as e:
        print(f"Error checking networks: {e}")
        return 1
    
    # Run the Archon container
    print("\n=== Starting darchon-docker-mcp container ===")
    cmd = [
        "docker", "run", "-d",
        "--name", "darchon-docker-mcp",
        "-p", "8505:8501",
        "-p", "8105:8100",
        "--network", "archon-network",
        "--add-host", "host.docker.internal:host-gateway"
    ]
    
    # Add environment variables if .env exists
    if env_args:
        cmd.extend(env_args)
    
    # Add image name
    cmd.append("darchon-docker-mcp:latest")
    
    if run_command(cmd) != 0:
        print("Error starting darchon-docker-mcp container")
        return 1
    
    # Wait a moment for the container to start
    time.sleep(2)
    
    # Connect container to supabase_default network
    print("\n=== Connecting container to supabase_default network ===")
    if run_command(["docker", "network", "connect", "supabase_default", "darchon-docker-mcp"]) != 0:
        print("Warning: Failed to connect container to supabase_default network")
    


    # Print success message
    print("\n=== darchon-docker-mcp is now running! ===")
    print("-> Access the Streamlit UI at: http://10.147.20.5:8505")
    print("-> Access the Langfuse at: http://10.147.20.5:8002 or via the streamlit page")
    print("-> Main service container is ready to use.")
    print("\nTo stop the services, run:")
    print("  docker stop darchon-docker-mcp")
    print("  docker rm darchon-docker-mcp")
    return 0

if __name__ == "__main__":
    exit(main())
