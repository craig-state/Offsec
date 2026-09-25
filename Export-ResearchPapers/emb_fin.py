#!/usr/bin/env python3
"""
Improved Template Bank + Enhanced Slot Filler Pipeline
======================================================

Embedding inversion via template bank scoring and margin-aware slot filling.
This is the improved version of emb_fin.py with four enhancements:

  1. Template Diversity Clustering — removes near-duplicate templates via
     greedy agglomerative clustering on pairwise cosine similarity.
  2. Two-Stage Narrowing — coarse pass on top-3 templates narrows the
     wordlist before the full tournament, dramatically reducing computation.
  3. Gap-Based Confidence — uses separation_ratio (best/second-best weighted
     score) for more robust confidence classification.
  4. Relative Threshold for Template Selection — replaces fixed top_k with
     a similarity-floor approach that adapts to the embedding landscape.

  Stage 1: Score template bank against target embedding -> threshold selection
  Stage 2: Diversity clustering -> diverse seed set
  Stage 3: Enhanced slot filling (two-stage narrowing, margin-aware,
           weighted consensus, gap-based confidence, progressive fill-and-lock)

Requirements (pip):
    pip install torch numpy transformers

Usage:
    python emb_fin_improved.py embeddings.npy --chunk 0 \\
        --templates templates.json --wordlist passwords.txt \\
        --slots PASSWORD --default-URL https://login.megacorpone.ai

    python emb_fin_improved.py embeddings.npy --all \\
        --templates templates.json --wordlist passwords.txt
"""

import sys
import json
import re
import gzip
import argparse
import numpy as np
import torch
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


# ============================================================================
# SECTION 1: BUILT-IN TEMPLATE BANKS
# ============================================================================

DOMAIN_TEMPLATES = {
    "credentials": [
        "Please navigate to {URL} and click on Need help signing in. The default password after resetting is {PASSWORD} which must be changed immediately.",
        "Visit {URL} to reset your password. Your temporary credential is {PASSWORD} and must be updated on first login.",
        "Access {URL} to complete password reset. Temporary password: {PASSWORD}.",
        "Your password has been reset. New password: {PASSWORD}. Login at {URL}.",
        "Password reset complete. Use {PASSWORD} at {URL}. Change immediately.",
        "Temporary password: {PASSWORD}. Reset at {URL}.",
        "Go to {URL} and click reset password. The default password is {PASSWORD}.",
        "Login at {URL} with temporary password {PASSWORD}. This expires in 24 hours.",
        "Access the portal at {URL} using your temporary password {PASSWORD}.",
        "Password: {PASSWORD}. Portal: {URL}. Must change on first login.",
        "Your new password is {PASSWORD}. Please visit {URL} to update it.",
        "Reset complete. Access {URL} with {PASSWORD}.",
        "API endpoint: {URL}, Key: {API_KEY}.",
        "Service URL: {URL} with API key {API_KEY}.",
        "Authentication token for {URL}: {API_KEY}.",
        "Production API: {URL}, Auth: {API_KEY}.",
        "Endpoint {URL} requires token {API_KEY}.",
        "Bearer token for {URL} is {API_KEY}.",
        "Service account credentials: endpoint {URL}, API key {API_KEY}.",
        "Database connection: host {URL}, password {PASSWORD}.",
        "Admin console at {URL} with password {PASSWORD}.",
        "SSH key for {URL}: {SSH_KEY}.",
        "Connection string: {URL} with secret {PASSWORD}.",
    ],
    "pii": [
        "Employee {NAME} salary adjusted to {SALARY} annually effective {DATE}.",
        "Compensation for {NAME}: base {SALARY}, bonus 15%.",
        "{NAME} hired at {SALARY} starting {DATE}.",
        "Salary increase for {NAME} to {SALARY}.",
        "Employee ID {EMPLOYEE_ID}: {NAME}, SSN ending {SSN_LAST4}.",
        "Personal info: {NAME}, DOB {DOB}, address {ADDRESS}.",
        "{NAME} contact: {PHONE}, {EMAIL}.",
        "Emergency contact for {NAME}: {EMERGENCY_CONTACT} at {PHONE}.",
        "Benefits enrollment for {NAME}: plan {PLAN_NAME}, premium {AMOUNT}.",
        "Medical claim for {NAME}: diagnosis {CODE}, amount {AMOUNT}.",
        "HIPAA record: patient {NAME}, MRN {MRN}.",
    ],
    "financial": [
        "Q{QUARTER} revenue: {AMOUNT}. Operating margin: {PERCENT}%.",
        "Budget approved: {AMOUNT} for {DEPARTMENT}.",
        "Invoice #{NUMBER} for {AMOUNT} due {DATE}.",
        "Wire transfer: {AMOUNT} to account {ACCOUNT}.",
        "Expense report by {NAME}: {AMOUNT}.",
        "Purchase order: {AMOUNT} for {VENDOR}.",
        "Credit facility: {AMOUNT} at {RATE}% from {BANK}.",
        "Revenue forecast: {AMOUNT} for FY{YEAR}.",
        "Acquisition: {COMPANY} for {AMOUNT}.",
        "Settlement: {AMOUNT} to {PARTY}. Confidential.",
    ],
    "infrastructure": [
        "Server {HOSTNAME} at {IP_ADDRESS}, admin password {PASSWORD}.",
        "VPN gateway: {URL}, credential {PASSWORD}.",
        "Kubernetes cluster: {URL}, token {API_KEY}.",
        "Database {DBNAME}: host {HOST}, port {PORT}, password {PASSWORD}.",
        "AWS account {ACCOUNT_ID}: access key {ACCESS_KEY}, secret {SECRET_KEY}.",
        "SSL certificate for {DOMAIN} expires {DATE}.",
        "DNS record: {HOSTNAME} -> {IP_ADDRESS}.",
        "Load balancer {NAME} endpoint: {URL}.",
        "Secrets manager: {URL}, master key {API_KEY}.",
        "CI/CD pipeline token: {API_KEY}.",
    ],
    "generic": [
        "{NAME} {ACTION} {OBJECT} on {DATE}.",
        "Document ID {NUMBER}: {DESCRIPTION}.",
        "Reference: {REFERENCE}. Amount: {AMOUNT}.",
        "Contact {NAME} at {EMAIL} or {PHONE}.",
        "Update: {DESCRIPTION}. Effective {DATE}.",
    ],
}

NEUTRAL_DEFAULTS = {
    "URL": "https://portal.company.com",
    "PASSWORD": "password123",
    "USERNAME": "admin",
    "API_KEY": "sk-prod-abc123",
    "TOKEN": "eyJhbGciOiJIUzI1NiJ9",
    "EMAIL": "admin@company.com",
    "IP_ADDRESS": "10.0.1.100",
    "PORT": "8443",
    "HOSTNAME": "srv-prod-01",
    "DATABASE": "prod_db",
    "SECRET": "s3cr3t_k3y_v4lu3",
    "DOMAIN": "company.com",
    "PATH": "/var/data/config",
    "HASH": "5f4dcc3b5aa765d61d8327deb882cf99",
    "VERSION": "2.1.0",
    "ENDPOINT": "/api/v1/auth",
    "ACCOUNT_ID": "ACC-78291",
    "REGION": "us-east-1",
    "CLUSTER": "prod-cluster-01",
    "CERTIFICATE": "cert-abc123.pem",
}


# ============================================================================
# SECTION 2: EMBEDDING ENGINE
# ============================================================================

class EmbeddingEngine:
    """
    Unified embedding engine with:
    - Sub-batched computation (GPU memory safety)
    - Relative-threshold template scoring (Improvement 4)
    - Diversity clustering (Improvement 1)
    - Single-text similarity + batch similarity
    - Embedding cache with statistics
    """

    def __init__(self, model_name: str, device: str = "auto", batch_size: int = 256):
        from transformers import AutoModel, AutoTokenizer

        if device == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device

        print(f"[Engine] Loading {model_name} on {self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.batch_size = batch_size

        # Cache (text -> embedding tensor)
        self._cache: Dict[str, torch.Tensor] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def get_embedding(self, text: str) -> torch.Tensor:
        """Get embedding for a single text (cached)."""
        if text in self._cache:
            self._cache_hits += 1
            return self._cache[text]

        self._cache_misses += 1

        inputs = self.tokenizer(
            text, return_tensors="pt",
            padding=True, truncation=True, max_length=512
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            token_emb = outputs.last_hidden_state
            mask = inputs['attention_mask'].unsqueeze(-1).expand(token_emb.size()).float()
            embedding = (torch.sum(token_emb * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)).squeeze()

        self._cache[text] = embedding
        return embedding

    def _embed_batch(self, texts: List[str]) -> torch.Tensor:
        """Embed a single sub-batch (must fit in GPU memory)."""
        inputs = self.tokenizer(
            texts, return_tensors="pt",
            padding=True, truncation=True, max_length=512
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            token_emb = outputs.last_hidden_state
            mask = inputs['attention_mask'].unsqueeze(-1).expand(token_emb.size()).float()
            emb = torch.sum(token_emb * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)

        del inputs, outputs, token_emb, mask
        if self.device == "cuda":
            torch.cuda.empty_cache()

        return emb

    def get_embeddings_batch(self, texts: List[str]) -> torch.Tensor:
        """Batch embedding with sub-batching to avoid OOM."""
        if not texts:
            return torch.tensor([]).to(self.device)

        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]
            emb = self._embed_batch(batch_texts)
            all_embeddings.append(emb)

        return torch.cat(all_embeddings, dim=0)

    def score_against_target(self, texts: List[str], target_emb: torch.Tensor) -> List[float]:
        """Compute cosine similarities between texts and target embedding."""
        if not texts:
            return []
        text_embs = self.get_embeddings_batch(texts)
        target_exp = target_emb.unsqueeze(0).expand(len(texts), -1)
        sims = torch.nn.functional.cosine_similarity(text_embs, target_exp, dim=1)
        return sims.tolist()

    def compute_similarity(self, text: str, target_emb: torch.Tensor) -> float:
        """Compute cosine similarity for a single text."""
        text_emb = self.get_embedding(text)
        return torch.nn.functional.cosine_similarity(
            text_emb.unsqueeze(0), target_emb.unsqueeze(0)
        ).item()

    def compute_similarities_batch(self, texts: List[str], target_emb: torch.Tensor) -> List[float]:
        """Batch similarity computation (alias for score_against_target)."""
        return self.score_against_target(texts, target_emb)

    def find_top_k(
        self,
        templates: List[str],
        target_emb: torch.Tensor,
        top_k: int = 20,
        verbose: bool = True,
        similarity_floor_pct: float = 0.85,
        max_seeds: int = 50,
        min_seeds: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        Score all templates against target and return candidates using
        relative threshold selection (Improvement 4).

        Instead of a fixed top_k, uses a similarity floor relative to the
        top-1 score:
          threshold = top1_similarity * similarity_floor_pct
        All templates above that threshold are included, capped at max_seeds
        and floored at min_seeds.

        When top_k == max_seeds == min_seeds (i.e. --top-k was used as a
        fixed override), this degrades gracefully to the original behavior.
        """
        if verbose:
            print(f"\n[Scoring] Evaluating {len(templates):,} templates...")

        all_sims = []
        total = len(templates)
        progress_interval = max(1, (total // self.batch_size) // 10) * self.batch_size

        for i in range(0, total, self.batch_size):
            batch = templates[i:i + self.batch_size]
            batch_embs = self._embed_batch(batch)
            target_exp = target_emb.unsqueeze(0).expand(len(batch), -1)
            sims = torch.nn.functional.cosine_similarity(batch_embs, target_exp, dim=1)
            all_sims.extend(sims.tolist())

            del batch_embs, target_exp, sims

            if verbose and i > 0 and i % progress_interval == 0:
                print(f"    {i:,}/{total:,} scored...")

        if verbose:
            print(f"    {total:,}/{total:,} scored.")

        pairs = list(zip(templates, all_sims))
        pairs.sort(key=lambda x: x[1], reverse=True)

        # --- Improvement 4: Relative threshold selection ---
        if not pairs:
            return []

        top1_sim = pairs[0][1]
        threshold = top1_sim * similarity_floor_pct

        # Count how many pass the threshold
        qualifying = [p for p in pairs if p[1] >= threshold]
        n_qualifying = len(qualifying)

        # Apply min/max bounds
        n_selected = max(min_seeds, min(n_qualifying, max_seeds))
        # Also don't exceed available templates
        n_selected = min(n_selected, len(pairs))

        top = pairs[:n_selected]

        if verbose:
            print(f"    Threshold {threshold:.4f}: {n_qualifying} templates qualify "
                  f"(using {n_selected})")
            print(f"    Top-1: {top[0][1]:.4f}  |  Top-{len(top)}: {top[-1][1]:.4f}")

        return top

    def select_diverse_templates(
        self,
        top_templates: List[Tuple[str, float]],
        target_emb: torch.Tensor,
        diversity_threshold: float = 0.85,
        min_diverse: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        Improvement 1: Template Diversity Clustering.

        Given a list of (template, similarity) pairs, remove near-duplicates
        using greedy agglomerative clustering based on pairwise cosine
        similarity of template embeddings.

        Algorithm:
          1. Compute embeddings for all top templates.
          2. Compute pairwise cosine similarity matrix.
          3. Greedily iterate through templates (in order of descending
             target similarity). Add a template to the "kept" set only if
             its maximum cosine similarity to any already-kept template is
             below diversity_threshold.
          4. Enforce min_diverse: if fewer than min_diverse are kept, relax
             by adding the next-best templates that were skipped.

        Returns the filtered list of (template, similarity) tuples.
        """
        if len(top_templates) <= 1:
            return top_templates

        # Compute embeddings for all top templates
        template_texts = [t for t, _ in top_templates]
        template_embs = self.get_embeddings_batch(template_texts)

        # Normalize for cosine similarity
        norms = template_embs.norm(dim=1, keepdim=True).clamp(min=1e-9)
        normed = template_embs / norms

        # Pairwise cosine similarity matrix
        pairwise_sim = torch.mm(normed, normed.t())

        # Greedy selection (templates already sorted by target similarity desc)
        kept_indices = []
        skipped_indices = []

        for i in range(len(top_templates)):
            if not kept_indices:
                # Always keep the best template
                kept_indices.append(i)
                continue

            # Max similarity to any already-kept template
            max_sim_to_kept = max(
                pairwise_sim[i, j].item() for j in kept_indices
            )

            if max_sim_to_kept < diversity_threshold:
                kept_indices.append(i)
            else:
                skipped_indices.append(i)

        # Enforce minimum diversity count
        if len(kept_indices) < min_diverse:
            needed = min_diverse - len(kept_indices)
            # Add back skipped templates in their original order (best first)
            for idx in skipped_indices[:needed]:
                kept_indices.append(idx)
            kept_indices.sort()

        result = [top_templates[i] for i in kept_indices]
        return result

    def clear_cache(self):
        """Clear embedding cache."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._cache),
        }


# ============================================================================
# SECTION 3: TEMPLATE LOADING
# ============================================================================

class TemplateLoader:
    """Load templates from bank directory, JSON file, or hardcoded fallback."""

    @staticmethod
    def load(bank_path: Optional[str] = None,
             templates_json: Optional[str] = None,
             max_templates: int = 100000) -> Tuple[List[str], str]:
        """Load templates from configured source."""
        if bank_path:
            templates = TemplateLoader.from_bank(bank_path, max_templates)
            return templates, f"bank: {bank_path}"
        elif templates_json:
            templates = TemplateLoader.from_json(templates_json)
            if max_templates and len(templates) > max_templates:
                templates = templates[:max_templates]
            return templates, f"json: {templates_json}"
        else:
            templates = TemplateLoader.get_fallback()
            return templates, "hardcoded fallback (59 templates)"

    @staticmethod
    def from_bank(bank_path: str, max_count: int = 100000) -> List[str]:
        """Load from pre-generated bank (sharded .json.gz)."""
        bank_dir = Path(bank_path)
        if not bank_dir.exists():
            raise FileNotFoundError(f"Template bank not found: {bank_path}")

        templates = []
        shard_files = sorted(bank_dir.rglob("templates_*.json.gz"))

        if not shard_files:
            raise FileNotFoundError(f"No template shards found in {bank_path}")

        for shard_path in shard_files:
            with gzip.open(shard_path, 'rt') as f:
                data = json.load(f)
                templates.extend(data.get("templates", []))
            if len(templates) >= max_count:
                templates = templates[:max_count]
                break

        return templates

    @staticmethod
    def from_json(json_path: str) -> List[str]:
        """Load from single JSON file (from template_generator.py)."""
        with open(json_path, 'r') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("templates", [])

    @staticmethod
    def get_fallback() -> List[str]:
        """Return hardcoded fallback templates."""
        all_templates = []
        for templates in DOMAIN_TEMPLATES.values():
            all_templates.extend(templates)
        return all_templates


# ============================================================================
# SECTION 4: SLOT RESULT + ENHANCED SLOT FILLER
# ============================================================================

@dataclass
class SlotResult:
    """Result of filling a single slot."""
    value: str
    similarity: float
    margin: float
    template_consensus: float
    confidence: str
    competing_values: List[Tuple[str, float]]
    z_score: float = 0.0
    z_gap: float = 0.0
    percentile: float = 0.0
    margin_z_score: float = 0.0
    margin_z_gap: float = 0.0
    raw_consensus: float = 0.0
    separation_ratio: float = 0.0


class EnhancedSlotFiller:
    """
    Enhanced slot filler with improvements over the base version:

    1. Margin-aware scoring  -- computes a neutral baseline per template
       and uses (raw_sim - baseline) margins for winner selection and
       z-score computation.

    2. Weighted consensus -- each template's vote is weighted by its
       base similarity to the target (better templates count more).

    3. Progressive fill-and-lock -- two-pass slot filling where Pass 1
       fills all slots independently, high-confidence results are locked,
       and Pass 2 re-fills weak slots with locked context.

    4. Two-Stage Narrowing (Improvement 2) -- coarse pass on top-3
       templates narrows the wordlist before the full tournament.

    5. Gap-Based Confidence (Improvement 3) -- uses separation_ratio
       for more robust confidence classification.
    """

    DEFAULT_WORDLISTS = {
        "PASSWORD": [
            "Password123!", "Welcome123!", "Changeme1!", "TempPass1!",
            "Summer2024!", "Winter2024!", "Spring2024!", "Fall2024!",
            "Company123!", "Admin123!", "User12345!", "Secure123!",
            "Access2024!", "Login123!", "Reset123!", "Temp1234!",
        ],
        "URL": [
            "https://portal.company.com", "https://login.internal.com",
            "https://sso.corp.local", "https://auth.internal.net",
            "https://access.corp.com", "https://hr.company.com",
        ],
        "API_KEY": [
            "sk-prod-abc123", "sk-test-xyz789", "api-key-12345",
            "token-abcdef", "key-123456789",
        ],
    }

    def __init__(self, engine: EmbeddingEngine, config):
        self.engine = engine
        self.config = config
        self.wordlists = {}
        # Merge neutral defaults: built-in + user overrides
        self.neutral_defaults = dict(NEUTRAL_DEFAULTS)
        if getattr(config, 'neutral_defaults', None):
            self.neutral_defaults.update(config.neutral_defaults)
            pairs = ", ".join(f"{k}={v}" for k, v in config.neutral_defaults.items())
            print(f"[SlotFiller] Neutral defaults active: {pairs}")

    def load_wordlist(self, path: str, slot_type: str = "PASSWORD"):
        """Load external wordlist file."""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            words = [line.strip() for line in f if line.strip()]
        self.wordlists[slot_type] = words
        print(f"[SlotFiller] Loaded {len(words):,} entries for {slot_type}")

    def _get_wordlist(self, slot_type: str) -> List[str]:
        if slot_type in self.wordlists:
            return self.wordlists[slot_type]
        if slot_type in self.DEFAULT_WORDLISTS:
            return self.DEFAULT_WORDLISTS[slot_type]
        return []

    def _run_template_tournament(
        self,
        templates_subset: List[Tuple[str, float]],
        slot_name: str,
        wordlist: List[str],
        target_emb: torch.Tensor,
        locked_values: Optional[Dict[str, str]],
        label: str = "",
    ) -> Tuple[List[tuple], Dict[str, list], Dict[str, list]]:
        """
        Run per-template tournament on a set of templates with a given wordlist.

        Returns:
            template_winners: list of (template, winner_value, winner_sim,
                              raw_margin, winner_margin, base_similarity)
            all_value_scores: dict mapping value -> list of raw sims
            all_value_margin_scores: dict mapping value -> list of margin sims
        """
        placeholder = "{" + slot_name + "}"

        valid = [(t, s) for t, s in templates_subset if placeholder in t]
        if not valid:
            return [], {v: [] for v in wordlist}, {v: [] for v in wordlist}

        template_winners = []
        all_value_scores = {v: [] for v in wordlist}
        all_value_margin_scores = {v: [] for v in wordlist}

        for idx, (template, base_similarity) in enumerate(valid):
            if label:
                print(f"    {label} Template {idx + 1}/{len(valid)} "
                      f"({len(wordlist):,} candidates)...",
                      end="\r", flush=True)
            else:
                print(f"    Template {idx + 1}/{len(valid)} "
                      f"({len(wordlist):,} candidates)...",
                      end="\r", flush=True)

            # Pre-fill all OTHER placeholders with locked values or neutral defaults
            prefilled = template
            for other_slot in re.findall(r'\{([A-Z_]+)\}', template):
                if other_slot != slot_name:
                    other_ph = "{" + other_slot + "}"
                    if locked_values and other_slot in locked_values:
                        default_val = locked_values[other_slot]
                    else:
                        default_val = self.neutral_defaults.get(other_slot, "example")
                    prefilled = prefilled.replace(other_ph, default_val)

            # Compute baseline: template with ALL slots neutral-filled
            baseline_text = prefilled.replace(
                placeholder,
                self.neutral_defaults.get(slot_name, "example")
            )
            baseline_sim = self.engine.compute_similarity(baseline_text, target_emb)

            # Score candidates (raw similarities)
            texts = [prefilled.replace(placeholder, v) for v in wordlist]
            raw_sims = self.engine.score_against_target(texts, target_emb)

            # Margin scores: improvement over neutral baseline
            margin_sims = [s - baseline_sim for s in raw_sims]

            # Winner selection uses margin_sims (largest margin wins)
            sorted_by_margin = sorted(
                zip(wordlist, raw_sims, margin_sims),
                key=lambda x: x[2],
                reverse=True,
            )
            winner_value = sorted_by_margin[0][0]
            winner_sim = sorted_by_margin[0][1]
            winner_margin = sorted_by_margin[0][2]
            second_margin = sorted_by_margin[1][2] if len(sorted_by_margin) > 1 else 0.0
            raw_margin = winner_margin - second_margin

            template_winners.append((
                template, winner_value, winner_sim, raw_margin,
                winner_margin, base_similarity,
            ))

            for value, sim, msim in zip(wordlist, raw_sims, margin_sims):
                all_value_scores[value].append(sim)
                all_value_margin_scores[value].append(msim)

        print()
        return template_winners, all_value_scores, all_value_margin_scores

    def fill_slot(
        self,
        top_k_templates: List[Tuple[str, float]],
        slot_name: str,
        target_emb: torch.Tensor,
        locked_values: Optional[Dict[str, str]] = None,
    ) -> SlotResult:
        """
        Fill a single slot using top-K templates with:
        - Two-stage narrowing (Improvement 2)
        - Margin-aware scoring
        - Weighted consensus
        - Gap-based confidence (Improvement 3)
        """

        wordlist = self._get_wordlist(slot_name)
        if not wordlist:
            return SlotResult(
                value=f"[NO_WORDLIST_{slot_name}]",
                similarity=0.0, margin=0.0, template_consensus=0.0,
                confidence="NO_WORDLIST", competing_values=[],
                separation_ratio=0.0,
            )

        placeholder = "{" + slot_name + "}"

        # Only use templates that contain this slot
        valid = [(t, s) for t, s in top_k_templates if placeholder in t]
        if not valid:
            return SlotResult(
                value=f"[NO_TEMPLATE_{slot_name}]",
                similarity=0.0, margin=0.0, template_consensus=0.0,
                confidence="NO_TEMPLATE", competing_values=[],
                separation_ratio=0.0,
            )

        # ============================================================
        # Improvement 2: Two-Stage Narrowing
        # ============================================================
        # Stage 1 (coarse): Run full wordlist against top-3 templates
        # to narrow down candidates.
        # Stage 2 (full): Run survivors through ALL templates.
        # ============================================================

        use_two_stage = len(wordlist) > 200 and len(valid) > 3

        if use_two_stage:
            # --- Stage 1: Coarse pass with top-3 templates ---
            coarse_templates = valid[:3]
            print(f"    [Stage 1/2] Coarse pass: {len(wordlist):,} candidates "
                  f"x {len(coarse_templates)} templates")

            coarse_winners, coarse_scores, coarse_margins = self._run_template_tournament(
                coarse_templates, slot_name, wordlist, target_emb,
                locked_values, label="[Stage 1]",
            )

            # Collect survivors: values that appeared in top-10 by margin
            # for ANY coarse template
            survivors_set = set()

            for value in wordlist:
                if coarse_margins[value]:
                    # Check if this value was in top-10 by margin for any template
                    for tmpl_idx in range(len(coarse_templates)):
                        # Get this value's margin for this template
                        if tmpl_idx < len(coarse_margins[value]):
                            pass  # margins are stored per-template in order

                    # Simpler approach: compute avg margin, take top candidates
                    pass

            # Compute per-value average margin across coarse templates
            value_avg_margins = []
            for v in wordlist:
                if coarse_margins[v]:
                    avg_m = float(np.mean(coarse_margins[v]))
                else:
                    avg_m = float('-inf')
                value_avg_margins.append((v, avg_m))

            value_avg_margins.sort(key=lambda x: x[1], reverse=True)

            # Also collect per-template top-10 by margin
            # We need to reconstruct per-template rankings
            for tmpl_idx in range(len(coarse_templates)):
                tmpl_values_margins = []
                for v in wordlist:
                    if tmpl_idx < len(coarse_margins[v]):
                        tmpl_values_margins.append((v, coarse_margins[v][tmpl_idx]))
                tmpl_values_margins.sort(key=lambda x: x[1], reverse=True)
                for v, _ in tmpl_values_margins[:10]:
                    survivors_set.add(v)

            # Always include at least top-200 unique candidates by avg margin
            for v, _ in value_avg_margins[:200]:
                survivors_set.add(v)

            survivors = [v for v in wordlist if v in survivors_set]
            print(f"    [Stage 1/2] Narrowed to {len(survivors):,} survivors "
                  f"from {len(wordlist):,} candidates")

            # --- Stage 2: Full pass with ALL templates ---
            print(f"    [Stage 2/2] Full pass: {len(survivors):,} candidates "
                  f"x {len(valid)} templates")

            template_winners, all_value_scores, all_value_margin_scores = \
                self._run_template_tournament(
                    valid, slot_name, survivors, target_emb,
                    locked_values, label="[Stage 2]",
                )

            # Use survivors as the effective wordlist for statistics
            effective_wordlist = survivors

        else:
            # --- Single-stage (original behavior for small wordlists) ---
            template_winners, all_value_scores, all_value_margin_scores = \
                self._run_template_tournament(
                    valid, slot_name, wordlist, target_emb, locked_values,
                )
            effective_wordlist = wordlist

        # --- Cross-template weighted consensus ---
        value_wins: Dict[str, Dict[str, Any]] = {}
        for _, winner, sim, raw_margin, winner_margin, base_sim in template_winners:
            if winner not in value_wins:
                value_wins[winner] = {
                    "count": 0, "weight": 0.0,
                    "sims": [], "margins": [], "margin_scores": [],
                }
            value_wins[winner]["count"] += 1
            value_wins[winner]["weight"] += base_sim
            value_wins[winner]["sims"].append(sim)
            value_wins[winner]["margins"].append(raw_margin)
            value_wins[winner]["margin_scores"].append(winner_margin)

        if not value_wins:
            return SlotResult(
                value=f"[NO_WINNERS_{slot_name}]",
                similarity=0.0, margin=0.0, template_consensus=0.0,
                confidence="NO_TEMPLATE", competing_values=[],
                separation_ratio=0.0,
            )

        # Best value by weighted vote
        best_value = max(value_wins.keys(), key=lambda v: value_wins[v]["weight"])
        best_info = value_wins[best_value]

        # Weighted consensus
        total_weight = sum(info["weight"] for info in value_wins.values())
        weighted_consensus = best_info["weight"] / total_weight if total_weight > 0 else 0.0
        raw_consensus = best_info["count"] / len(valid)

        avg_sim = float(np.mean(best_info["sims"]))
        avg_margin = float(np.mean(best_info["margins"]))

        competing = sorted(
            [(v, float(np.mean(all_value_scores[v])))
             for v in effective_wordlist
             if v != best_value and all_value_scores.get(v)],
            key=lambda x: x[1], reverse=True
        )[:5]

        # --- Z-score: raw similarities ---
        avg_sims_per_value = []
        for v in effective_wordlist:
            if all_value_scores.get(v):
                avg_sims_per_value.append(float(np.mean(all_value_scores[v])))
            else:
                avg_sims_per_value.append(0.0)
        avg_sims_array = np.array(avg_sims_per_value)

        sim_mean = float(np.mean(avg_sims_array))
        sim_std = float(np.std(avg_sims_array))

        if sim_std > 1e-9:
            z_score = (avg_sim - sim_mean) / sim_std
        else:
            z_score = 0.0

        sorted_avg_sims = sorted(avg_sims_per_value, reverse=True)
        second_avg_sim = sorted_avg_sims[1] if len(sorted_avg_sims) > 1 else sim_mean
        if sim_std > 1e-9:
            z_gap = (avg_sim - second_avg_sim) / sim_std
        else:
            z_gap = 0.0

        percentile = float(np.mean(avg_sims_array < avg_sim)) * 100.0

        # --- Z-score: margin-based ---
        avg_margins_per_value = []
        for v in effective_wordlist:
            if all_value_margin_scores.get(v):
                avg_margins_per_value.append(float(np.mean(all_value_margin_scores[v])))
            else:
                avg_margins_per_value.append(0.0)
        avg_margins_array = np.array(avg_margins_per_value)

        margin_mean = float(np.mean(avg_margins_array))
        margin_std = float(np.std(avg_margins_array))

        best_avg_margin_score = float(np.mean(best_info["margin_scores"])) if best_info["margin_scores"] else 0.0

        if margin_std > 1e-9:
            margin_z_score = (best_avg_margin_score - margin_mean) / margin_std
        else:
            margin_z_score = 0.0

        sorted_avg_margins = sorted(avg_margins_per_value, reverse=True)
        second_avg_margin = sorted_avg_margins[1] if len(sorted_avg_margins) > 1 else margin_mean
        if margin_std > 1e-9:
            margin_z_gap = (best_avg_margin_score - second_avg_margin) / margin_std
        else:
            margin_z_gap = 0.0

        # ============================================================
        # Improvement 3: Gap-Based Confidence with separation_ratio
        # ============================================================
        effective_z = max(z_score, margin_z_score)
        effective_gap = max(z_gap, margin_z_gap)
        consensus = weighted_consensus  # use weighted for thresholds

        # Compute separation_ratio: best weighted score / second-best weighted score
        sorted_by_weight = sorted(
            value_wins.items(),
            key=lambda x: x[1]["weight"],
            reverse=True,
        )
        best_weight = sorted_by_weight[0][1]["weight"]
        if len(sorted_by_weight) > 1:
            second_weight = sorted_by_weight[1][1]["weight"]
            if second_weight > 1e-9:
                separation_ratio = best_weight / second_weight
            else:
                separation_ratio = float('inf')
        else:
            separation_ratio = float('inf')

        # Gap-based confidence tiers
        if (separation_ratio >= 3.0 and raw_consensus >= 0.6):
            confidence = "HIGH"
        elif (effective_z > 4.0 and effective_gap > 1.5):
            confidence = "HIGH"
        elif (separation_ratio >= 1.8 and raw_consensus >= 0.4):
            confidence = "MEDIUM"
        elif (effective_z > 2.5 and consensus >= 0.7):
            confidence = "MEDIUM"
        elif (separation_ratio >= 1.3 or
              (effective_z > 2.0 and raw_consensus >= 0.3)):
            confidence = "LOW"
        else:
            confidence = "LIKELY_FALSE_POSITIVE"

        return SlotResult(
            value=best_value,
            similarity=avg_sim,
            margin=avg_margin,
            template_consensus=weighted_consensus,
            confidence=confidence,
            competing_values=competing,
            z_score=z_score,
            z_gap=z_gap,
            percentile=percentile,
            margin_z_score=margin_z_score,
            margin_z_gap=margin_z_gap,
            raw_consensus=raw_consensus,
            separation_ratio=separation_ratio,
        )

    def fill_all_slots(
        self,
        top_k_templates: List[Tuple[str, float]],
        target_emb: torch.Tensor,
    ) -> Dict[str, Any]:
        """
        Fill all (or filtered) slots with progressive fill-and-lock.

        Pass 1: fill all slots independently.
        Pass 2: lock high-confidence slots, re-fill weak slots with
                 locked context.  Only update if the new result improves.
        """

        # Discover all slots in top-K templates
        all_slots = set()
        for t, _ in top_k_templates:
            all_slots.update(re.findall(r'\{([A-Z_]+)\}', t))

        # Filter to target slots if specified
        if self.config.target_slots:
            all_slots = all_slots & set(self.config.target_slots)

        if not all_slots:
            return {
                "filled_template": top_k_templates[0][0],
                "slots": {},
                "high_confidence_slots": [],
                "likely_false_positives": [],
            }

        # --- Pass 1: fill all slots independently ---
        results: Dict[str, SlotResult] = {}
        for slot in sorted(all_slots):
            print(f"\n  [Slot: {slot}] Pass 1 — testing across "
                  f"{len(top_k_templates)} seed templates...")

            results[slot] = self.fill_slot(top_k_templates, slot, target_emb)

        # --- Determine locks ---
        locked = {
            s: r.value
            for s, r in results.items()
            if r.z_score > 2.0 and r.confidence != "LIKELY_FALSE_POSITIVE"
        }

        # --- Pass 2: re-fill non-locked slots with locked context ---
        if locked:
            locked_display = ", ".join(f"{s}={v}" for s, v in locked.items())
            print(f"\n  [Progressive] Locked slots: {locked_display}")

            for slot in sorted(all_slots):
                if slot not in locked:
                    print(f"\n  [Slot: {slot}] Pass 2 — re-filling with "
                          f"locked context...")

                    new_result = self.fill_slot(
                        top_k_templates, slot, target_emb,
                        locked_values=locked,
                    )
                    # Only update if improved
                    if new_result.z_score > results[slot].z_score:
                        if self.config.verbose:
                            print(f"    Improved: z_score {results[slot].z_score:.2f}"
                                  f" -> {new_result.z_score:.2f}")
                        results[slot] = new_result
                    else:
                        if self.config.verbose:
                            print(f"    No improvement (z_score {new_result.z_score:.2f}"
                                  f" <= {results[slot].z_score:.2f}), keeping Pass 1 result")

        # --- Build output dict ---
        output_slots = {}
        for slot, result in results.items():
            output_slots[slot] = {
                "value": result.value,
                "similarity": result.similarity,
                "margin": result.margin,
                "consensus": result.template_consensus,
                "raw_consensus": result.raw_consensus,
                "confidence": result.confidence,
                "competing": result.competing_values[:3],
                "z_score": result.z_score,
                "z_gap": result.z_gap,
                "percentile": result.percentile,
                "margin_z_score": result.margin_z_score,
                "margin_z_gap": result.margin_z_gap,
                "separation_ratio": result.separation_ratio,
            }

        # Build filled template from the best-matching template
        filled_template = top_k_templates[0][0]
        for slot, info in output_slots.items():
            if info["confidence"] != "LIKELY_FALSE_POSITIVE":
                filled_template = filled_template.replace("{" + slot + "}", info["value"])

        return {
            "filled_template": filled_template,
            "slots": output_slots,
            "high_confidence_slots": [s for s, i in output_slots.items()
                                      if i["confidence"] == "HIGH"],
            "likely_false_positives": [s for s, i in output_slots.items()
                                       if i["confidence"] == "LIKELY_FALSE_POSITIVE"],
        }


# ============================================================================
# SECTION 5: PIPELINE (Orchestrator)
# ============================================================================

class SlotPipeline:
    """
    Orchestrates the attack pipeline:

      Stage 1: Template bank scoring -> relative threshold selection
      Stage 2: Diversity clustering -> diverse seed set
      Stage 3: Enhanced slot filling (two-stage narrowing, margin-aware,
               weighted, gap-based confidence, progressive)
    """

    def __init__(self, config):
        self.config = config
        self.engine = EmbeddingEngine(
            config.embedding_model,
            config.device,
            config.batch_size,
        )

    def attack_chunk(
        self,
        target_embedding: np.ndarray,
        chunk_idx: int = 0,
    ) -> Dict[str, Any]:
        """Execute the full pipeline on a single embedding chunk."""

        target_emb = torch.tensor(
            target_embedding, dtype=torch.float32
        ).to(self.engine.device)

        result: Dict[str, Any] = {
            "chunk_idx": chunk_idx,
            "timestamp": datetime.now().isoformat(),
        }

        print(f"\n[Chunk {chunk_idx}]")

        # ==============================================================
        # Stage 1: Template bank scoring -> relative threshold selection
        # ==============================================================
        print(f"\n  Scoring template bank...")

        templates, source = TemplateLoader.load(
            bank_path=self.config.bank_path,
            templates_json=self.config.templates_json,
            max_templates=self.config.max_templates,
        )
        print(f"    Templates loaded: {len(templates):,} from {source}")

        top_k = self.engine.find_top_k(
            templates, target_emb,
            top_k=self.config.top_k,
            verbose=self.config.verbose,
            similarity_floor_pct=self.config.similarity_floor_pct,
            max_seeds=self.config.max_seeds,
            min_seeds=self.config.min_seeds,
        )

        result["template_source"] = source
        result["templates_scored"] = len(templates)
        result["top_k_before_diversity"] = len(top_k)

        # ==============================================================
        # Stage 1.5: Diversity clustering (Improvement 1)
        # ==============================================================
        pool_size = len(top_k)
        top_k = self.engine.select_diverse_templates(
            top_k, target_emb,
            diversity_threshold=self.config.diversity_threshold,
        )
        print(f"    Selected {len(top_k)} diverse templates from top-{pool_size}")

        result["top_k"] = [
            {"template": t, "similarity": s} for t, s in top_k[:5]
        ]

        if self.config.verbose:
            print(f"\n    Top-{len(top_k)} templates:")
            for i, (t, s) in enumerate(top_k[:5]):
                print(f"      {i+1}. [{s:.4f}] {t[:65]}...")
            if len(top_k) > 5:
                print(f"      ... ({len(top_k) - 5} more)")

        # ==============================================================
        # Stage 2: Enhanced slot filling
        # ==============================================================
        print(f"\n  Slot filling...")

        filler = EnhancedSlotFiller(self.engine, self.config)
        if self.config.wordlist_path:
            filler.load_wordlist(self.config.wordlist_path)

        slot_results = filler.fill_all_slots(top_k, target_emb)

        result["slot_filling"] = {
            "top_k_count": len(top_k),
            "top_1_similarity": top_k[0][1] if top_k else 0,
            "top_1_template": top_k[0][0] if top_k else "",
            "filled_template": slot_results.get("filled_template", ""),
            "slots": slot_results.get("slots", {}),
            "high_confidence_slots": slot_results.get("high_confidence_slots", []),
            "likely_false_positives": slot_results.get("likely_false_positives", []),
        }

        # ==============================================================
        # SUMMARY
        # ==============================================================
        self._print_summary(result, top_k, slot_results)

        return result

    def _print_summary(
        self,
        result: Dict,
        top_k: List[Tuple[str, float]],
        slot_results: Dict,
    ):
        """Print pipeline summary."""
        verbose = self.config.verbose
        print(f"\n--- Chunk {result['chunk_idx']} ---")

        sf = result.get("slot_filling", {})
        if sf.get("slots"):
            sim = sf.get("top_1_similarity", 0)
            t1 = sf.get("top_1_template", "")
            print(f"\n  Best template match ({sim*100:.1f}% similarity):")
            print(f"    \"{t1[:70]}...\"")

            n_templates = sf.get("top_k_count", 0)
            print(f"\n  Extracted values:")
            for slot, info in sf["slots"].items():
                conf = info.get("confidence", "?")
                rc = info.get("raw_consensus", 0)
                sr = info.get("separation_ratio", 0)
                label = _user_confidence(conf, rc, n_templates, sr)
                print(f"    {slot} = {info['value']}")
                print(f"      {label}")
                if verbose:
                    wc = info.get("consensus", 0)
                    z = info.get("z_score", 0)
                    zg = info.get("z_gap", 0)
                    mz = info.get("margin_z_score", 0)
                    mgz = info.get("margin_z_gap", 0)
                    margin = info.get("margin", 0)
                    print(f"      [tier={conf} z={z:.2f} gap={zg:.2f} mz={mz:.2f} "
                          f"mgap={mgz:.2f} wcons={wc:.0%} rcons={rc:.0%} "
                          f"margin={margin:.4f} sep_ratio={sr:.1f}x]")
                if sf.get("filled_template"):
                    print(f"      Reconstructed: \"{sf['filled_template'][:70]}...\"")
        else:
            print(f"\n  No slots filled")

    def attack_chunks(
        self,
        embeddings: np.ndarray,
        chunk_indices: List[int],
    ) -> List[Dict[str, Any]]:
        """Attack multiple chunks."""
        results = []
        for idx in chunk_indices:
            if idx >= len(embeddings):
                print(f"[!] Chunk {idx} out of range (max {len(embeddings)-1})")
                continue
            results.append(self.attack_chunk(embeddings[idx], chunk_idx=idx))
        return results


# ============================================================================
# SECTION 6: CONFIGURATION
# ============================================================================

@dataclass
class PipelineConfig:
    """Configuration for the slot filling pipeline."""

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "auto"
    batch_size: int = 256

    # Template sources
    bank_path: Optional[str] = None
    templates_json: Optional[str] = None
    max_templates: int = 100000

    # Top-K
    top_k: int = 20

    # Improvement 4: Relative threshold for template selection
    similarity_floor_pct: float = 0.85
    max_seeds: int = 50
    min_seeds: int = 5

    # Improvement 1: Diversity clustering threshold
    diversity_threshold: float = 0.85

    # Slot filling
    wordlist_path: Optional[str] = None
    target_slots: Optional[List[str]] = None
    neutral_defaults: Optional[Dict[str, str]] = None

    verbose: bool = False


# ============================================================================
# SECTION 7: OUTPUT FORMATTER
# ============================================================================

def _user_confidence(
    conf: str,
    rcons: float = 0,
    n_templates: int = 0,
    separation_ratio: float = 0.0,
) -> str:
    """
    Map internal tier to user-friendly strength label with agreement info
    and separation ratio (Improvement 3).
    """
    agrees = round(rcons * n_templates) if n_templates else 0
    sep_str = ""
    if separation_ratio and separation_ratio != float('inf') and separation_ratio > 0:
        sep_str = f", {separation_ratio:.1f}x ahead of runner-up"
    elif separation_ratio == float('inf'):
        sep_str = ", no runner-up"

    if conf == "HIGH":
        if n_templates:
            return f"Strong — {agrees}/{n_templates} templates agree{sep_str}"
        return "Strong"
    elif conf == "MEDIUM":
        if n_templates:
            return f"Moderate — {agrees}/{n_templates} templates agree{sep_str}, worth verifying"
        return "Moderate — worth verifying"
    elif conf == "LOW":
        if rcons >= 0.7 and n_templates:
            return f"Likely — {agrees}/{n_templates} templates agree{sep_str}"
        elif n_templates:
            return f"Weak — {agrees}/{n_templates} templates agree{sep_str}"
        return "Weak"
    else:
        return "Unlikely — insufficient evidence"


def _result_marker(conf: str) -> str:
    """Return marker for result line."""
    if conf == "HIGH":
        return "+++"
    elif conf == "MEDIUM":
        return " ++"
    elif conf == "LOW":
        return "  +"
    else:
        return "  -"


def _format_number(n) -> str:
    """Format a number with comma separators."""
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)


def format_results(results: List[Dict], verbose: bool = False) -> str:
    """Format results for display."""

    output = []
    output.append("\n========================================")
    output.append("  RESULTS SUMMARY")
    output.append("========================================")

    validated = []
    unvalidated = []
    false_positives = []

    for r in results:
        sf = r.get("slot_filling", {})
        n_templates = sf.get("top_k_count", 0)
        for slot, info in sf.get("slots", {}).items():
            entry = {
                "chunk": r.get("chunk_idx", "?"),
                "slot": slot,
                "value": info["value"],
                "similarity": info["similarity"],
                "margin": info["margin"],
                "consensus": info["consensus"],
                "raw_consensus": info.get("raw_consensus", 0),
                "confidence": info["confidence"],
                "z_score": info.get("z_score", 0),
                "z_gap": info.get("z_gap", 0),
                "margin_z_score": info.get("margin_z_score", 0),
                "margin_z_gap": info.get("margin_z_gap", 0),
                "percentile": info.get("percentile", 0),
                "n_templates": n_templates,
                "separation_ratio": info.get("separation_ratio", 0),
            }

            if info["confidence"] == "HIGH":
                validated.append(entry)
            elif info["confidence"] in ["MEDIUM", "LOW"]:
                unvalidated.append(entry)
            else:
                false_positives.append(entry)

    all_entries = validated + unvalidated + false_positives
    if all_entries:
        output.append("\n  Extracted values:\n")
        for c in all_entries:
            rc = c['raw_consensus']
            nt = c['n_templates']
            sr = c.get('separation_ratio', 0)
            marker = _result_marker(c['confidence'])
            label = _user_confidence(c['confidence'], rc, nt, sr)
            output.append(f"    {marker} {c['slot']} = {c['value']}")
            output.append(f"        {label}")
            output.append(f"        Chunk {c['chunk']} "
                          f"| Best template: {c['similarity']*100:.1f}% match"
                          f" | Sep ratio: {sr:.1f}x")
            if verbose:
                output.append(
                    f"        [tier={c['confidence']} "
                    f"z={c['z_score']:.2f} gap={c['z_gap']:.2f} "
                    f"mz={c['margin_z_score']:.2f} "
                    f"mgap={c['margin_z_gap']:.2f} "
                    f"margin={c['margin']:.4f} "
                    f"pctl={c['percentile']:.1f}% "
                    f"sep_ratio={sr:.1f}x]")

    # Stats
    scored = "?"
    if results:
        scored = _format_number(results[0].get("templates_scored", "?"))
    output.append(f"\n  Stats: {len(results)} chunk(s) analyzed, "
                  f"{scored} templates scored")
    output.append(f"  Validated: {len(validated)} "
                  f"| Needs verification: {len(unvalidated)} "
                  f"| Rejected: {len(false_positives)}")

    return "\n".join(output)


# ============================================================================
# SECTION 8: CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Improved Template Bank + Enhanced Slot Filler Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single chunk
  python emb_fin_improved.py embeddings.npy --chunk 0 \\
      --templates templates.json --wordlist passwords.txt \\
      --slots PASSWORD --default-URL https://login.megacorpone.ai

  # Multiple chunks
  python emb_fin_improved.py embeddings.npy --chunks 0,1,2 \\
      --templates templates.json --wordlist passwords.txt

  # All chunks
  python emb_fin_improved.py embeddings.npy --all \\
      --templates templates.json --wordlist passwords.txt

  # Fill PASSWORD slot with custom URL context
  python emb_fin_improved.py embeddings.npy --chunk 0 \\
      --templates templates.json --wordlist passwords.txt \\
      --slots PASSWORD \\
      --default-URL https://login.mycompany.com --default-USERNAME admin

  # Use relative threshold instead of fixed top-k
  python emb_fin_improved.py embeddings.npy --chunk 0 \\
      --templates templates.json --wordlist passwords.txt \\
      --similarity-floor 0.80 --max-seeds 40 --min-seeds 10

  # Adjust diversity threshold
  python emb_fin_improved.py embeddings.npy --chunk 0 \\
      --templates templates.json --wordlist passwords.txt \\
      --diversity-threshold 0.90
        """
    )

    parser.add_argument('embeddings_file', type=str, help='Path to embeddings.npy')

    # Chunk selection
    parser.add_argument('--chunk', type=int, default=None, help='Single chunk index')
    parser.add_argument('--chunks', type=str, default=None,
                        help='Comma-separated chunk indices')
    parser.add_argument('--all', action='store_true', help='Attack all chunks')
    parser.add_argument('--max-chunks', type=int, default=50,
                        help='Max chunks when using --all (default: 50)')

    # Templates
    parser.add_argument('--templates', type=str, default=None,
                        help='Template JSON file (from template_generator.py)')
    parser.add_argument('--bank', type=str, default=None,
                        help='Template bank directory (sharded .json.gz)')
    parser.add_argument('--max-templates', type=int, default=100000,
                        help='Max templates to load (default: 100000)')

    # Top-K (kept as alias for fixed mode)
    parser.add_argument('--top-k', type=int, default=20,
                        help='Number of top seed templates for consensus (default: 20). '
                             'Sets both max-seeds and min-seeds for fixed mode.')

    # Improvement 4: Relative threshold args
    parser.add_argument('--similarity-floor', type=float, default=0.85,
                        help='Similarity floor as fraction of top-1 (default: 0.85)')
    parser.add_argument('--max-seeds', type=int, default=None,
                        help='Max templates to keep after threshold (default: 50)')
    parser.add_argument('--min-seeds', type=int, default=None,
                        help='Min templates to keep (default: 5)')

    # Improvement 1: Diversity clustering
    parser.add_argument('--diversity-threshold', type=float, default=0.85,
                        help='Max pairwise similarity for diversity clustering (default: 0.85)')

    # Slot filling
    parser.add_argument('--wordlist', type=str, default=None,
                        help='Wordlist file for slot filling')
    parser.add_argument('--slots', type=str, default=None,
                        help='Target slots (comma-separated, e.g. PASSWORD,URL)')

    # Model / device
    parser.add_argument('--model', type=str,
                        default='sentence-transformers/all-MiniLM-L6-v2',
                        help='Embedding model (default: all-MiniLM-L6-v2)')
    parser.add_argument('--device', type=str, default='auto',
                        help='Device: auto, cuda, cpu, mps')
    parser.add_argument('--batch-size', type=int, default=256,
                        help='Embedding batch size (default: 256)')

    # Output
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Save JSON results to file')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show full technical metrics in output')

    args, remaining = parser.parse_known_args()

    # Parse --default-SLOTNAME VALUE args
    slot_defaults = {}
    i = 0
    while i < len(remaining):
        if remaining[i].startswith('--default-'):
            slot_name = remaining[i][len('--default-'):].upper().replace('-', '_')
            if i + 1 < len(remaining) and not remaining[i + 1].startswith('--'):
                slot_defaults[slot_name] = remaining[i + 1]
                i += 2
            else:
                parser.error(f"{remaining[i]} requires a value")
        else:
            parser.error(f"Unrecognized argument: {remaining[i]}")
            i += 1

    # --- Handle --top-k as alias for fixed mode ---
    # If --top-k is explicitly provided and --max-seeds/--min-seeds are not,
    # use top_k as both max and min (fixed mode behavior).
    if args.max_seeds is None and args.min_seeds is None:
        # Check if --top-k was explicitly provided (not default)
        # We detect this by checking if it differs from default or
        # if max_seeds/min_seeds were not set
        max_seeds = args.top_k if args.top_k != 20 else 50
        min_seeds = args.top_k if args.top_k != 20 else 5
        # If top_k was explicitly set to 20 but user wanted fixed mode,
        # they would need to also set max/min. For backward compat,
        # if top_k != 20 we treat it as fixed mode.
        if args.top_k != 20:
            max_seeds = args.top_k
            min_seeds = args.top_k
        else:
            max_seeds = 50
            min_seeds = 5
    else:
        max_seeds = args.max_seeds if args.max_seeds is not None else 50
        min_seeds = args.min_seeds if args.min_seeds is not None else 5

    # Load embeddings
    print(f"\n[+] Loading: {args.embeddings_file}")
    embeddings = np.load(args.embeddings_file)
    if len(embeddings.shape) == 1:
        embeddings = embeddings.reshape(1, -1)
    print(f"    Shape: {embeddings.shape}")

    # Determine chunks
    if args.all:
        chunk_indices = list(range(min(len(embeddings), args.max_chunks)))
    elif args.chunks:
        chunk_indices = [int(c.strip()) for c in args.chunks.split(',')]
    elif args.chunk is not None:
        chunk_indices = [args.chunk]
    else:
        chunk_indices = [0]

    # Build config
    config = PipelineConfig(
        embedding_model=args.model,
        device=args.device,
        batch_size=args.batch_size,
        bank_path=args.bank,
        templates_json=args.templates,
        max_templates=args.max_templates,
        top_k=args.top_k,
        similarity_floor_pct=args.similarity_floor,
        max_seeds=max_seeds,
        min_seeds=min_seeds,
        diversity_threshold=args.diversity_threshold,
        wordlist_path=args.wordlist,
        target_slots=([s.strip().upper() for s in args.slots.split(',')]
                      if args.slots else None),
        neutral_defaults=slot_defaults if slot_defaults else None,
        verbose=args.verbose,
    )

    # Run pipeline
    pipeline = SlotPipeline(config)
    results = pipeline.attack_chunks(embeddings, chunk_indices)

    # Display
    print(format_results(results, verbose=config.verbose))

    # Save
    if args.output:
        output_data = {
            "pipeline": "template+slot (improved)",
            "timestamp": datetime.now().isoformat(),
            "embeddings_file": args.embeddings_file,
            "config": {
                "embedding_model": config.embedding_model,
                "top_k": config.top_k,
                "similarity_floor_pct": config.similarity_floor_pct,
                "max_seeds": config.max_seeds,
                "min_seeds": config.min_seeds,
                "diversity_threshold": config.diversity_threshold,
                "templates_json": config.templates_json,
            },
            "results": results,
        }

        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\n[+] Results saved to {args.output}")

    return results


if __name__ == "__main__":
    main()
