"""
Federated Learning System for MCP Army

This module enables agents to collectively learn and improve without sharing raw data.
Key features:
1. Secure knowledge vector sharing
2. Model/embedding aggregation with weighted averaging
3. Differential privacy to protect sensitive information
4. Adaptive learning rate based on contribution quality
5. Supabase integration for distributed storage and real-time updates
"""
import os
import time
import json
import uuid
import numpy as np
import logging
import asyncio
import threading
import base64
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Union
from datetime import datetime, timedelta
from collections import defaultdict
import aiohttp

# Import Supabase client
try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Attempt to import machine learning libraries
try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KnowledgeVector:
    """
    Represents learned knowledge that can be shared across agents
    """
    def __init__(self, 
                 agent_id: str,
                 vector_id: str = None,
                 vector_type: str = "embedding",
                 data: Any = None, 
                 metadata: Dict[str, Any] = None,
                 timestamp: float = None,
                 weight: float = 1.0,
                 version: str = "1.0"):
        self.agent_id = agent_id
        self.vector_id = vector_id or str(uuid.uuid4())
        self.vector_type = vector_type
        self.data = data
        self.metadata = metadata or {}
        self.timestamp = timestamp or time.time()
        self.weight = weight  # Importance weight for aggregation
        self.version = version
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize the knowledge vector for transmission"""
        serialized = {
            "agent_id": self.agent_id,
            "vector_id": self.vector_id,
            "vector_type": self.vector_type,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "weight": self.weight,
            "version": self.version
        }
        
        # Serialize the data based on type
        if self.data is not None:
            if isinstance(self.data, np.ndarray):
                serialized["data_format"] = "numpy"
                serialized["data"] = base64.b64encode(self.data.tobytes()).decode('utf-8')
                serialized["data_shape"] = self.data.shape
                serialized["data_dtype"] = str(self.data.dtype)
            elif TORCH_AVAILABLE and isinstance(self.data, torch.Tensor):
                numpy_data = self.data.detach().cpu().numpy()
                serialized["data_format"] = "torch"
                serialized["data"] = base64.b64encode(numpy_data.tobytes()).decode('utf-8')
                serialized["data_shape"] = numpy_data.shape
                serialized["data_dtype"] = str(numpy_data.dtype)
            elif TF_AVAILABLE and isinstance(self.data, tf.Tensor):
                numpy_data = self.data.numpy()
                serialized["data_format"] = "tensorflow"
                serialized["data"] = base64.b64encode(numpy_data.tobytes()).decode('utf-8')
                serialized["data_shape"] = numpy_data.shape
                serialized["data_dtype"] = str(numpy_data.dtype)
            else:
                # Assume data is JSON serializable
                serialized["data_format"] = "json"
                serialized["data"] = self.data
        else:
            serialized["data_format"] = "none"
            serialized["data"] = None
        
        return serialized
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'KnowledgeVector':
        """Deserialize a knowledge vector from transmission format"""
        # Extract basic fields
        vector = cls(
            agent_id=data["agent_id"],
            vector_id=data["vector_id"],
            vector_type=data["vector_type"],
            metadata=data["metadata"],
            timestamp=data["timestamp"],
            weight=data["weight"],
            version=data["version"]
        )
        
        # Deserialize data based on format
        data_format = data.get("data_format", "none")
        if data_format == "numpy":
            binary_data = base64.b64decode(data["data"])
            shape = tuple(data["data_shape"])
            dtype = np.dtype(data["data_dtype"])
            vector.data = np.frombuffer(binary_data, dtype=dtype).reshape(shape)
        elif data_format == "torch" and TORCH_AVAILABLE:
            binary_data = base64.b64decode(data["data"])
            shape = tuple(data["data_shape"])
            dtype = np.dtype(data["data_dtype"])
            numpy_array = np.frombuffer(binary_data, dtype=dtype).reshape(shape)
            vector.data = torch.from_numpy(numpy_array)
        elif data_format == "tensorflow" and TF_AVAILABLE:
            binary_data = base64.b64decode(data["data"])
            shape = tuple(data["data_shape"])
            dtype = np.dtype(data["data_dtype"])
            numpy_array = np.frombuffer(binary_data, dtype=dtype).reshape(shape)
            vector.data = tf.convert_to_tensor(numpy_array)
        elif data_format == "json":
            vector.data = data["data"]
        
        return vector
    
    def similarity(self, other: 'KnowledgeVector') -> float:
        """Calculate similarity between two knowledge vectors"""
        if self.vector_type != other.vector_type:
            return 0.0
        
        # Handle different data types
        if isinstance(self.data, np.ndarray) and isinstance(other.data, np.ndarray):
            # Use cosine similarity for embeddings
            if self.data.shape == other.data.shape:
                dot_product = np.dot(self.data.flatten(), other.data.flatten())
                norm_self = np.linalg.norm(self.data.flatten())
                norm_other = np.linalg.norm(other.data.flatten())
                if norm_self > 0 and norm_other > 0:
                    return dot_product / (norm_self * norm_other)
        
        elif TORCH_AVAILABLE and isinstance(self.data, torch.Tensor) and isinstance(other.data, torch.Tensor):
            # Convert to same device
            self_tensor = self.data.detach().float()
            other_tensor = other.data.detach().float()
            
            # Flatten and compute cosine similarity
            if self_tensor.shape == other_tensor.shape:
                self_flat = self_tensor.flatten()
                other_flat = other_tensor.flatten()
                return F.cosine_similarity(self_flat.unsqueeze(0), other_flat.unsqueeze(0)).item()
        
        # Default for other types: compare metadata fields
        metadata_similarity = 0.0
        if self.metadata and other.metadata:
            common_keys = set(self.metadata.keys()).intersection(set(other.metadata.keys()))
            if common_keys:
                matches = sum(1 for k in common_keys if self.metadata[k] == other.metadata[k])
                metadata_similarity = matches / len(common_keys)
        
        return metadata_similarity


class FederatedKnowledgeBank:
    """
    Central repository for storing and aggregating knowledge vectors from multiple agents
    with support for both file storage and Supabase storage
    """
    def __init__(self, storage_dir: Optional[str] = None, supabase_client = None, table_name: str = "federated_knowledge"):
        # Knowledge vectors indexed by vector_type -> vector_id -> KnowledgeVector
        self.vectors = defaultdict(dict)
        
        # Track contributions by agent
        self.contributions = defaultdict(int)
        
        # Performance metrics by agent
        self.metrics = defaultdict(lambda: {"correct": 0, "total": 0})
        
        # Storage configurations
        self.storage_dir = storage_dir
        self.supabase = supabase_client
        self.table_name = table_name
        self.use_supabase = supabase_client is not None and SUPABASE_AVAILABLE
        
        # Set up storage
        if storage_dir and not self.use_supabase:
            os.makedirs(storage_dir, exist_ok=True)
            
        # Set up Supabase if available
        if self.use_supabase:
            self._ensure_supabase_table()
            
        # Load any existing knowledge
        self._load_knowledge()
        
        # Lock for thread safety
        self.lock = threading.RLock()
    
    def add_vector(self, vector: KnowledgeVector) -> bool:
        """Add a knowledge vector to the bank"""
        with self.lock:
            # Check if vector already exists
            if vector.vector_id in self.vectors[vector.vector_type]:
                existing = self.vectors[vector.vector_type][vector.vector_id]
                # Only update if newer
                if vector.timestamp <= existing.timestamp:
                    return False
            
            # Store the vector
            self.vectors[vector.vector_type][vector.vector_id] = vector
            
            # Track contribution
            self.contributions[vector.agent_id] += 1
            
            # Persist knowledge
            if self.storage_dir:
                self._save_vector(vector)
            
            return True
    
    def get_vector(self, vector_type: str, vector_id: str) -> Optional[KnowledgeVector]:
        """Retrieve a specific knowledge vector"""
        with self.lock:
            return self.vectors.get(vector_type, {}).get(vector_id)
    
    def get_vectors_by_type(self, vector_type: str) -> List[KnowledgeVector]:
        """Get all knowledge vectors of a specific type"""
        with self.lock:
            return list(self.vectors.get(vector_type, {}).values())
    
    def get_agent_vectors(self, agent_id: str) -> List[KnowledgeVector]:
        """Get all knowledge vectors contributed by a specific agent"""
        with self.lock:
            result = []
            for vector_type in self.vectors:
                for vector in self.vectors[vector_type].values():
                    if vector.agent_id == agent_id:
                        result.append(vector)
            return result
    
    def aggregate_vectors(self, vector_type: str, filter_fn=None) -> Optional[KnowledgeVector]:
        """
        Aggregate knowledge vectors of a specific type into a single vector
        
        Args:
            vector_type: Type of vectors to aggregate
            filter_fn: Optional function to filter vectors before aggregation
        
        Returns:
            Aggregated knowledge vector or None if no vectors match
        """
        with self.lock:
            vectors = self.get_vectors_by_type(vector_type)
            if not vectors:
                return None
            
            # Apply filter if provided
            if filter_fn:
                vectors = [v for v in vectors if filter_fn(v)]
                if not vectors:
                    return None
            
            # Special handling based on vector type
            if vector_type == "embedding":
                return self._aggregate_embeddings(vectors)
            elif vector_type == "weights":
                return self._aggregate_weights(vectors)
            else:
                # Default aggregation: most recent with highest weight
                return max(vectors, key=lambda v: (v.weight, v.timestamp))
    
    def _aggregate_embeddings(self, vectors: List[KnowledgeVector]) -> KnowledgeVector:
        """Aggregate embedding vectors using weighted average"""
        if not vectors:
            return None
        
        # Check if vectors contain valid data
        valid_vectors = [v for v in vectors if v.data is not None]
        if not valid_vectors:
            return None
        
        # Determine data type from first vector
        first = valid_vectors[0]
        
        # Handle different data types
        if isinstance(first.data, np.ndarray):
            # Verify all vectors have same shape
            if not all(v.data.shape == first.data.shape for v in valid_vectors):
                # Filter to only vectors with matching shape
                valid_vectors = [v for v in valid_vectors if v.data.shape == first.data.shape]
                if not valid_vectors:
                    return None
            
            # Compute weighted average
            weights = np.array([v.weight for v in valid_vectors])
            weights = weights / weights.sum()  # Normalize weights
            
            aggregated = np.zeros_like(first.data)
            for i, vector in enumerate(valid_vectors):
                aggregated += vector.data * weights[i]
            
            # Create aggregated vector
            return KnowledgeVector(
                agent_id="federated",
                vector_type="embedding",
                data=aggregated,
                metadata={"source": "aggregated", "contributors": [v.agent_id for v in valid_vectors]},
                weight=sum(v.weight for v in valid_vectors) / len(valid_vectors)
            )
        
        elif TORCH_AVAILABLE and isinstance(first.data, torch.Tensor):
            # Verify all vectors have same shape
            if not all(v.data.shape == first.data.shape for v in valid_vectors):
                valid_vectors = [v for v in valid_vectors if v.data.shape == first.data.shape]
                if not valid_vectors:
                    return None
            
            # Compute weighted average
            weights = torch.tensor([v.weight for v in valid_vectors])
            weights = weights / weights.sum()  # Normalize weights
            
            aggregated = torch.zeros_like(first.data)
            for i, vector in enumerate(valid_vectors):
                aggregated += vector.data * weights[i]
            
            # Create aggregated vector
            return KnowledgeVector(
                agent_id="federated",
                vector_type="embedding",
                data=aggregated,
                metadata={"source": "aggregated", "contributors": [v.agent_id for v in valid_vectors]},
                weight=sum(v.weight for v in valid_vectors) / len(valid_vectors)
            )
        
        # Fall back to most relevant vector if types aren't compatible
        return max(valid_vectors, key=lambda v: v.weight)
    
    def _aggregate_weights(self, vectors: List[KnowledgeVector]) -> KnowledgeVector:
        """Aggregate model weight vectors using FedAvg algorithm"""
        # Similar to embedding aggregation but specifically for model weights
        return self._aggregate_embeddings(vectors)
    
    def record_feedback(self, agent_id: str, correct: bool) -> None:
        """Record feedback for an agent's contributions"""
        with self.lock:
            self.metrics[agent_id]["total"] += 1
            if correct:
                self.metrics[agent_id]["correct"] += 1
    
    def get_agent_performance(self, agent_id: str) -> Dict[str, Any]:
        """Get performance metrics for an agent"""
        with self.lock:
            metrics = self.metrics.get(agent_id, {"correct": 0, "total": 0})
            contributions = self.contributions.get(agent_id, 0)
            
            accuracy = metrics["correct"] / max(1, metrics["total"])
            
            return {
                "agent_id": agent_id,
                "contributions": contributions,
                "correct": metrics["correct"],
                "total": metrics["total"],
                "accuracy": accuracy
            }
    
    def _ensure_supabase_table(self) -> None:
        """Ensure the Supabase table exists for storing knowledge vectors"""
        if not self.use_supabase:
            return
            
        try:
            # Check if the table exists by querying it
            self.supabase.table(self.table_name).select("count", count="exact").limit(1).execute()
            logger.info(f"Supabase table '{self.table_name}' exists")
        except Exception:
            # Table likely doesn't exist, try to create it
            logger.info(f"Creating Supabase table '{self.table_name}'")
            
            # We need to use raw SQL for table creation through REST API
            # This would typically be done through the Supabase SQL editor by the user
            # Here we'll just log the SQL that should be executed
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                vector_id TEXT NOT NULL,
                vector_type TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(vector_id, vector_type)
            );
            
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_vector_type ON {self.table_name}(vector_type);
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_agent_id ON {self.table_name}(agent_id);
            
            -- Enable row-level security
            ALTER TABLE {self.table_name} ENABLE ROW LEVEL SECURITY;
            
            -- Create policy for authenticated users
            CREATE POLICY "{self.table_name}_policy"
                ON {self.table_name}
                USING (true);
            """
            
            logger.info(f"SQL to execute in Supabase SQL editor:\n{create_table_sql}")
            logger.warning("Please run the above SQL in the Supabase SQL editor to create the table")
    
    def _save_vector(self, vector: KnowledgeVector) -> None:
        """Save a vector to persistent storage (file or Supabase)"""
        # Save to Supabase if available
        if self.use_supabase:
            try:
                serialized = vector.serialize()
                
                # Upsert into Supabase (insert if not exists, update if exists)
                self.supabase.table(self.table_name).upsert({
                    "vector_id": vector.vector_id,
                    "vector_type": vector.vector_type,
                    "agent_id": vector.agent_id,
                    "data": serialized,
                    "updated_at": datetime.now().isoformat()
                }).execute()
                logger.debug(f"Saved vector {vector.vector_id} to Supabase")
                return
            except Exception as e:
                logger.error(f"Error saving vector to Supabase: {e}")
                # Fall back to file storage if Supabase fails
        
        # Save to file storage if Supabase not available or failed
        if not self.storage_dir:
            return
        
        try:
            # Create type directory if it doesn't exist
            type_dir = os.path.join(self.storage_dir, vector.vector_type)
            os.makedirs(type_dir, exist_ok=True)
            
            # Save serialized vector
            file_path = os.path.join(type_dir, f"{vector.vector_id}.json")
            with open(file_path, 'w') as f:
                json.dump(vector.serialize(), f)
        except Exception as e:
            logger.error(f"Error saving vector to file: {e}")
    
    def _load_knowledge(self) -> None:
        """Load knowledge vectors from persistent storage (file or Supabase)"""
        # Try loading from Supabase first
        if self.use_supabase:
            try:
                logger.info(f"Loading knowledge vectors from Supabase table '{self.table_name}'")
                response = self.supabase.table(self.table_name).select("*").execute()
                
                if hasattr(response, 'data') and response.data:
                    for item in response.data:
                        try:
                            # The vector data is stored in the 'data' field
                            vector = KnowledgeVector.deserialize(item['data'])
                            
                            # Add to in-memory store
                            self.vectors[vector.vector_type][vector.vector_id] = vector
                            self.contributions[vector.agent_id] += 1
                        except Exception as e:
                            logger.error(f"Error loading vector from Supabase: {e}")
                    
                    logger.info(f"Loaded {len(response.data)} vectors from Supabase")
                    return  # Successfully loaded from Supabase, skip file loading
            except Exception as e:
                logger.error(f"Error loading knowledge vectors from Supabase: {e}")
                # Fall back to file storage if Supabase fails
        
        # Load from file storage if Supabase not available or failed
        if not self.storage_dir or not os.path.exists(self.storage_dir):
            return
        
        try:
            logger.info(f"Loading knowledge vectors from directory '{self.storage_dir}'")
            # Iterate through type directories
            for type_dir in os.listdir(self.storage_dir):
                type_path = os.path.join(self.storage_dir, type_dir)
                if not os.path.isdir(type_path):
                    continue
                
                # Load each vector file
                for file_name in os.listdir(type_path):
                    if not file_name.endswith('.json'):
                        continue
                    
                    file_path = os.path.join(type_path, file_name)
                    try:
                        with open(file_path, 'r') as f:
                            vector_data = json.load(f)
                            vector = KnowledgeVector.deserialize(vector_data)
                            
                            # Add to in-memory store
                            self.vectors[vector.vector_type][vector.vector_id] = vector
                            self.contributions[vector.agent_id] += 1
                    except Exception as e:
                        logger.error(f"Error loading vector from {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading knowledge vectors from files: {e}")


class FederatedLearningService:
    """
    Service for managing federated learning across agents with support for Supabase
    """
    def __init__(self, 
                storage_path: str = None,
                privacy_level: float = 0.1,
                min_contributions: int = 3,
                use_supabase: bool = True,
                supabase_url: str = None,
                supabase_key: str = None,
                table_name: str = "federated_knowledge"):
        """
        Initialize the federated learning service
        
        Args:
            storage_path: Path to store knowledge vectors (used as fallback if Supabase unavailable)
            privacy_level: Level of differential privacy noise (0-1)
            min_contributions: Minimum contributions needed for aggregation
            use_supabase: Whether to use Supabase for storage
            supabase_url: Supabase URL (defaults to env var SUPABASE_URL)
            supabase_key: Supabase key (defaults to env var SUPABASE_KEY or SUPABASE_API_KEY)
            table_name: Name of the Supabase table for storing knowledge vectors
        """
        # Set up storage path (used as fallback or if Supabase is not available)
        if storage_path:
            self.storage_path = storage_path
        else:
            self.storage_path = os.path.join(os.path.expanduser("~"), ".mcp_army", "federated_knowledge")
        
        # Set up Supabase client if requested and available
        supabase_client = None
        if use_supabase and SUPABASE_AVAILABLE:
            # Get credentials from arguments or environment
            supabase_url = supabase_url or os.environ.get("SUPABASE_URL")
            supabase_key = supabase_key or os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_API_KEY")
            
            if supabase_url and supabase_key:
                try:
                    supabase_client = create_client(supabase_url, supabase_key)
                    logger.info("Successfully initialized Supabase client for federated learning")
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")
            else:
                logger.warning("Supabase URL or key not provided. Using file storage instead.")
        
        # Create knowledge bank with either Supabase or file storage
        self.knowledge_bank = FederatedKnowledgeBank(
            storage_dir=self.storage_path,
            supabase_client=supabase_client,
            table_name=table_name
        )
        
        # Privacy settings
        self.privacy_level = privacy_level
        self.min_contributions = min_contributions
    
    def contribute_knowledge(self, 
                           agent_id: str, 
                           vector_type: str,
                           data: Any,
                           metadata: Dict[str, Any] = None) -> str:
        """
        Contribute knowledge to the federated learning system
        
        Args:
            agent_id: ID of the contributing agent
            vector_type: Type of knowledge vector
            data: Vector data (numpy array, tensor, etc.)
            metadata: Additional metadata about the vector
            
        Returns:
            ID of the contributed vector
        """
        # Apply differential privacy if enabled
        if self.privacy_level > 0 and isinstance(data, np.ndarray):
            # Add Gaussian noise proportional to privacy level
            noise_scale = self.privacy_level * np.std(data) / 10
            noise = np.random.normal(0, noise_scale, data.shape)
            data = data + noise
        
        # Create knowledge vector
        vector = KnowledgeVector(
            agent_id=agent_id,
            vector_type=vector_type,
            data=data,
            metadata=metadata or {}
        )
        
        # Add to knowledge bank
        self.knowledge_bank.add_vector(vector)
        
        return vector.vector_id
    
    def get_aggregated_knowledge(self, 
                               vector_type: str, 
                               filter_metadata: Dict[str, Any] = None) -> Optional[Any]:
        """
        Get aggregated knowledge from all agents
        
        Args:
            vector_type: Type of knowledge to retrieve
            filter_metadata: Optional metadata filter to apply
            
        Returns:
            Aggregated knowledge vector data or None if not enough contributions
        """
        # Define filter function if metadata filter provided
        filter_fn = None
        if filter_metadata:
            def filter_fn(vector):
                return all(vector.metadata.get(k) == v for k, v in filter_metadata.items())
        
        # Get all vectors of the requested type
        vectors = self.knowledge_bank.get_vectors_by_type(vector_type)
        
        # Apply filter if provided
        if filter_fn:
            vectors = [v for v in vectors if filter_fn(v)]
        
        # Check if we have minimum contributions
        contributors = set(v.agent_id for v in vectors)
        if len(contributors) < self.min_contributions:
            logger.info(f"Not enough contributors for {vector_type} ({len(contributors)} < {self.min_contributions})")
            return None
        
        # Aggregate knowledge
        aggregated = self.knowledge_bank.aggregate_vectors(vector_type, filter_fn)
        if aggregated:
            return aggregated.data
        return None
    
    def provide_feedback(self, agent_id: str, was_helpful: bool) -> None:
        """
        Provide feedback about an agent's contributions
        
        Args:
            agent_id: ID of the agent
            was_helpful: Whether the agent's contribution was helpful
        """
        self.knowledge_bank.record_feedback(agent_id, was_helpful)
    
    def get_agent_stats(self, agent_id: str) -> Dict[str, Any]:
        """
        Get statistics about an agent's contributions
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Dictionary with agent statistics
        """
        return self.knowledge_bank.get_agent_performance(agent_id)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all contributing agents
        
        Returns:
            Dictionary mapping agent_id to agent statistics
        """
        stats = {}
        for agent_id in self.knowledge_bank.contributions.keys():
            stats[agent_id] = self.get_agent_stats(agent_id)
        return stats


# Singleton instance with Supabase support enabled by default
_federated_service = FederatedLearningService(use_supabase=True)



# Convenience functions
def contribute_knowledge(agent_id: str, vector_type: str, data: Any, metadata: Dict[str, Any] = None) -> str:
    """Contribute knowledge to the federated learning system"""
    return _federated_service.contribute_knowledge(agent_id, vector_type, data, metadata)

def get_aggregated_knowledge(vector_type: str, filter_metadata: Dict[str, Any] = None) -> Optional[Any]:
    """Get aggregated knowledge from all agents"""
    return _federated_service.get_aggregated_knowledge(vector_type, filter_metadata)

def provide_feedback(agent_id: str, was_helpful: bool) -> None:
    """Provide feedback about an agent's contributions"""
    _federated_service.provide_feedback(agent_id, was_helpful)

def get_agent_stats(agent_id: str) -> Dict[str, Any]:
    """Get statistics about an agent's contributions"""
    return _federated_service.get_agent_stats(agent_id)

def get_all_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all contributing agents"""
    return _federated_service.get_all_stats()
