"""
Simple Container Orchestration Service
Manages user backend containers on demand
"""
import docker
import uuid
import time
from typing import Dict, Optional

class ContainerOrchestrator:
    def __init__(self):
        self.client = docker.from_env()
        self.active_containers: Dict[str, dict] = {}
        
    def create_user_backend(self, user_id: str) -> Dict[str, str]:
        """
        Create a new backend container for a user
        Returns container info including access URL
        """
        # Generate unique container name
        container_name = f"user-{user_id}-{uuid.uuid4().hex[:8]}"
        
        # Define container configuration
        container_config = {
            'image': 'ai-agent-user-backend:latest',
            'name': container_name,
            'ports': {'8000/tcp': None},  # Random port assignment
            'environment': {
                'USER_ID': user_id,
                'SESSION_TOKEN': uuid.uuid4().hex
            },
            'detach': True,
            'restart_policy': {"Name": "unless-stopped"}
        }
        
        try:
            # Create and start container
            container = self.client.containers.run(**container_config)
            
            # Wait for container to be ready
            time.sleep(5)
            
            # Get assigned port
            container.reload()
            host_port = container.attrs['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
            
            # Store container info
            container_info = {
                'container_id': container.short_id,
                'container_name': container_name,
                'host_port': host_port,
                'access_url': f"http://YOUR_SERVER_IP:{host_port}",
                'status': 'running'
            }
            
            self.active_containers[user_id] = container_info
            
            return container_info
            
        except Exception as e:
            return {'error': str(e)}
    
    def stop_user_backend(self, user_id: str) -> bool:
        """
        Stop and remove a user's backend container
        """
        if user_id in self.active_containers:
            try:
                container_name = self.active_containers[user_id]['container_name']
                container = self.client.containers.get(container_name)
                container.stop()
                container.remove()
                del self.active_containers[user_id]
                return True
            except Exception:
                return False
        return False
    
    def get_container_status(self, user_id: str) -> Optional[Dict]:
        """
        Get the status of a user's backend container
        """
        return self.active_containers.get(user_id)

# Example usage:
# orchestrator = ContainerOrchestrator()
# container_info = orchestrator.create_user_backend("user123")
# print(container_info)