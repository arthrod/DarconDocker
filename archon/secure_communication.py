"""
Secure Agent Communication System for MCP Army

Provides enterprise-grade security for agent-to-agent communication including:
1. JWT-based authentication with role-based access control
2. Request signing and verification
3. Capability-based security model
4. Secure credential management
"""
import os
import jwt
import time
import uuid
import logging
import hashlib
import base64
from typing import Dict, List, Any, Optional, Union, Callable
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key, load_pem_public_key,
    Encoding, PrivateFormat, PublicFormat, NoEncryption
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_TOKEN_EXPIRY = 3600  # 1 hour in seconds
JWT_SECRET = os.environ.get("MCP_JWT_SECRET", "mcp_army_default_secret_key_change_this_in_production")
JWT_ALGORITHM = "HS256"


@dataclass
class AgentCredential:
    """Agent credential with identity and access information"""
    
    agent_id: str
    name: str
    roles: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    api_key: str = None
    public_key: str = None
    private_key: str = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        # Generate API key if not provided
        if not self.api_key:
            self.api_key = self._generate_api_key()
        
        # Generate keypair if not provided
        if not self.public_key or not self.private_key:
            self.private_key, self.public_key = self._generate_keypair()
    
    def _generate_api_key(self) -> str:
        """Generate a secure API key for this agent"""
        key_material = f"{self.agent_id}:{uuid.uuid4()}:{int(time.time())}"
        return hashlib.sha256(key_material.encode()).hexdigest()
    
    def _generate_keypair(self) -> tuple:
        """Generate an RSA keypair for signing and encryption"""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Get public key
        public_key = private_key.public_key()
        
        # Serialize keys to PEM format
        private_pem = private_key.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption()
        ).decode('utf-8')
        
        public_pem = public_key.public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        return private_pem, public_pem
    
    def create_jwt(self, expiry: int = DEFAULT_TOKEN_EXPIRY) -> str:
        """Create a JWT token for this agent"""
        now = int(time.time())
        
        payload = {
            "sub": self.agent_id,
            "name": self.name,
            "roles": self.roles,
            "scopes": self.scopes,
            "iat": now,
            "exp": now + expiry
        }
        
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def sign_request(self, payload: Dict[str, Any]) -> str:
        """Sign a request payload with the agent's private key"""
        # Serialize payload to string
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, sort_keys=True)
        else:
            payload_str = str(payload)
        
        # Load private key
        private_key = load_pem_private_key(
            self.private_key.encode(),
            password=None
        )
        
        # Create signature
        signature = private_key.sign(
            payload_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        # Return base64-encoded signature
        return base64.b64encode(signature).decode()


class CredentialManager:
    """Manages agent credentials and performs authentication/authorization"""
    
    def __init__(self):
        self.credentials = {}  # agent_id -> AgentCredential
        self.api_keys = {}  # api_key -> agent_id
    
    def register_agent(self, 
                       agent_id: str, 
                       name: str, 
                       roles: List[str] = None, 
                       scopes: List[str] = None) -> AgentCredential:
        """Register a new agent and get credentials"""
        credential = AgentCredential(
            agent_id=agent_id,
            name=name,
            roles=roles or ["agent"],
            scopes=scopes or []
        )
        
        # Store credential
        self.credentials[agent_id] = credential
        self.api_keys[credential.api_key] = agent_id
        
        return credential
    
    def get_credential(self, agent_id: str) -> Optional[AgentCredential]:
        """Get an agent's credential by ID"""
        return self.credentials.get(agent_id)
    
    def get_credential_by_api_key(self, api_key: str) -> Optional[AgentCredential]:
        """Get an agent's credential by API key"""
        agent_id = self.api_keys.get(api_key)
        if agent_id:
            return self.credentials.get(agent_id)
        return None
    
    def verify_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify a JWT token and return the payload if valid"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.PyJWTError as e:
            logger.warning(f"JWT validation failed: {e}")
            return None
    
    def verify_signature(self, 
                         agent_id: str, 
                         payload: Dict[str, Any], 
                         signature: str) -> bool:
        """Verify a request signature"""
        credential = self.get_credential(agent_id)
        if not credential or not credential.public_key:
            return False
        
        try:
            # Serialize payload to string
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, sort_keys=True)
            else:
                payload_str = str(payload)
            
            # Load public key
            public_key = load_pem_public_key(credential.public_key.encode())
            
            # Decode signature
            signature_bytes = base64.b64decode(signature)
            
            # Verify signature
            public_key.verify(
                signature_bytes,
                payload_str.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False
    
    def check_authorization(self, 
                           agent_id: str, 
                           required_roles: List[str] = None, 
                           required_scopes: List[str] = None) -> bool:
        """Check if an agent has the required roles and scopes"""
        credential = self.get_credential(agent_id)
        if not credential:
            return False
        
        # Check roles if required
        if required_roles:
            if not any(role in credential.roles for role in required_roles):
                return False
        
        # Check scopes if required
        if required_scopes:
            if not all(scope in credential.scopes for scope in required_scopes):
                return False
        
        return True


# Singleton instance
_credential_manager = CredentialManager()


# FastAPI middleware and decorator functions
def get_bearer_token(request) -> Optional[str]:
    """Extract bearer token from authorization header"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]  # Remove "Bearer " prefix


def verify_agent_auth(required_roles=None, required_scopes=None):
    """Decorator for FastAPI endpoints to verify agent authentication and authorization"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request object from kwargs - assumes FastAPI dependency injection
            request = None
            for arg in args:
                if hasattr(arg, "headers"):
                    request = arg
                    break
            
            if not request:
                for key, value in kwargs.items():
                    if hasattr(value, "headers"):
                        request = value
                        break
            
            if not request:
                raise ValueError("Could not find request object in function arguments")
            
            # Get token from authorization header
            token = get_bearer_token(request)
            if not token:
                return {"error": "Unauthorized", "detail": "Missing authentication token"}
            
            # Verify token
            payload = _credential_manager.verify_jwt(token)
            if not payload:
                return {"error": "Unauthorized", "detail": "Invalid authentication token"}
            
            # Check authorization
            agent_id = payload.get("sub")
            if not _credential_manager.check_authorization(
                agent_id, required_roles, required_scopes
            ):
                return {"error": "Forbidden", "detail": "Insufficient permissions"}
            
            # Add agent info to kwargs
            kwargs["agent_info"] = payload
            
            # Call original function
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# Convenience functions
def register_agent(agent_id: str, name: str, roles: List[str] = None, scopes: List[str] = None) -> AgentCredential:
    """Register a new agent and get credentials"""
    return _credential_manager.register_agent(agent_id, name, roles, scopes)

def get_credential(agent_id: str) -> Optional[AgentCredential]:
    """Get an agent's credential by ID"""
    return _credential_manager.get_credential(agent_id)

def create_agent_token(agent_id: str, expiry: int = DEFAULT_TOKEN_EXPIRY) -> Optional[str]:
    """Create a JWT token for an agent"""
    credential = _credential_manager.get_credential(agent_id)
    if credential:
        return credential.create_jwt(expiry)
    return None

def verify_agent_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify an agent's JWT token"""
    return _credential_manager.verify_jwt(token)
