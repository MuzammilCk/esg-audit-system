
import logging
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from services.privacy.redis_manager import RedisManager

logger = logging.getLogger(__name__)

# Standard PII entities to detect
PII_ENTITIES = [
    "PERSON", 
    "EMAIL_ADDRESS", 
    "PHONE_NUMBER", 
    "LOCATION", 
    "ORGANIZATION", 
    "IBAN_CODE", 
    "CREDIT_CARD", 
    "US_SSN",
    "UK_NHS"
]

class PIIMasker:
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        # Initialize Presidio engines. 
        # Note: AnalyzerEngine automatically loads the spaCy model 'en_core_web_lg' if available and default logic uses it.
        # We assume dependencies are installed.
        try:
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
            logger.info("Presidio engines initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Presidio engines: {e}")
            raise

    def mask_text(self, text: str, doc_id: str) -> Tuple[str, bool]:
        """
        Analyzes and masks PII in the text.
        Returns:
            Tuple[str, bool]: (masked_text, success)
        """
        if not text:
            return text, True

        try:
            # 1. Analyze text
            results = self.analyzer.analyze(text=text, entities=PII_ENTITIES, language='en')
            
            if not results:
                return text, True

            # 2. Prepare custom operators with counters
            # We need to map each specific entity instance to a specific placeholder <ENTITY_N>
            # Presidio's default anonymization replaces all instances of a type with the same operator or masks them.
            # To achieve <PERSON_1>, <PERSON_2> mapping, we need a custom approach.
            # We can use Presidio's `custom` operator but we need to pass a function or pre-calculate replacements.
            
            # Strategy: 
            # Iterate through results, generate placeholders, and build the mapping manually or semi-manually.
            # Presidio Anonymizer supports 'replace' operator. We can define specific operators for each entity type?
            # No, operators are per entity type.
            
            # Better approach for reversible mapping with unique counters:
            # Sort results by start index (reverse order to modify text without affecting indices of earlier entities).
            # But wait, we want to construct the mapping {"<PERSON_1>": "Jane Doe"}.
            
            # Let's do it manually using the analysis results. 
            # Presidio results give us start/end and entity type.
            
            # Sort results by start index descending
            results.sort(key=lambda x: x.start, reverse=True)
            
            mapping = {}
            counters = defaultdict(int)
            
            # We work on a list of characters for efficiency or string slicing
            text_chars = list(text)
            
            # To handle overlapping entities, Presidio usually filtering overlaps. 
            # We'll assume the analyzer output is clean or we might need `self.analyzer.analyze` to handle conflicts logic default.
            
            for result in results:
                entity_type = result.entity_type
                start = result.start
                end = result.end
                original_value = text[start:end]
                
                # Check conflict/overlap if necessary, but Presidio analyzer usually returns non-overlapping if configured?
                # Actually analyzer might return overlaps. We should filter.
                # Simple filter: check if this range overlaps with processed range?
                # Since we iterate in reverse order, if we modify text, we need to be careful.
                # But here we are just building replacements.
                
                counters[entity_type] += 1
                placeholder = f"<{entity_type}_{counters[entity_type]}>"
                
                # Store mapping (Placeholder -> Original)
                # Note: counters are incremented in reverse order of appearance in text if we iterate reverse!
                # To get <PERSON_1> for the FIRST person, we should process results in forward order first to assign IDs, 
                # then apply replacements in reverse order.
                
            # Correct Strategy:
            # 1. Process forward to assign placeholders
            results.sort(key=lambda x: x.start)
            
            # Filter overlaps provided by Presidio logic usually handles this, 
            # but let's ensure we don't process same char twice.
            # A simple way is to keep a mask of indices.
            
            processed_results = []
            used_indices = set()
            
            # Re-initialize counters for forward pass assignment
            counters = defaultdict(int)
            entity_mappings = [] # list of (start, end, placeholder)
            
            for result in results:
                # Basic overlap check
                if any(i in used_indices for i in range(result.start, result.end)):
                    continue
                
                for i in range(result.start, result.end):
                    used_indices.add(i)
                
                counters[result.entity_type] += 1
                placeholder = f"<{result.entity_type}_{counters[result.entity_type]}>"
                
                original_text = text[result.start:result.end]
                mapping[placeholder] = original_text
                
                entity_mappings.append((result.start, result.end, placeholder))
                
            # 2. Apply replacements in reverse order to correct positions
            entity_mappings.sort(key=lambda x: x[0], reverse=True)
            
            masked_text_list = list(text)
            for start, end, placeholder in entity_mappings:
                masked_text_list[start:end] = list(placeholder)
            
            masked_text = "".join(masked_text_list)
            
            # 3. Store mapping
            if mapping:
                self.redis_manager.store_mapping(doc_id, mapping)
            
            return masked_text, True

        except Exception as e:
            logger.error(f"Error in masking text for {doc_id}: {e}")
            return text, False
