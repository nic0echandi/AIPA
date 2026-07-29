#!/usr/bin/env python3
"""
Anonymize superagent.log: replace emails and domains with generic placeholders
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

def anonymize_log(input_file, output_file):
    """
    Anonymize sensitive data in log file:
    - Replace emails with analyst.one@company.com, analyst.two@company.com, etc.
    - Replace domain names with generic equivalents
    - Keep timestamps and log structure intact
    """
    
    # Mapping dictionaries
    email_mapping = {}
    domain_mapping = {}
    email_counter = 1
    domain_counter = 1
    
    # Domain replacements
    DOMAIN_MAP = {
        'movi.com.ar': 'company.com',
        'gmail.com': 'mail.example.com',
        'andeshosting.net': 'hosting.example.com',
        'magnificentminds.org': 'org.example.com',
        'engage.mail.microsoft': 'mail.service.com',
        'mail-campaign.com': 'campaign.example.com',
        'daleplay.la': 'service.example.la',
        'itcollege.com.ar': 'academy.example.com',
        'taller.andeshosting.net': 'taller.example.com',
    }
    
    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    
    anonymized_lines = []
    
    for line in lines:
        # Extract all emails
        emails = re.findall(r'[\w.-]+@[\w.-]+\.\w+', line)
        
        # Replace emails
        modified_line = line
        for email in set(emails):
            if email not in email_mapping:
                # Get domain
                local_part, domain = email.rsplit('@', 1)
                
                # Replace domain if it's in our mapping
                if domain in DOMAIN_MAP:
                    new_domain = DOMAIN_MAP[domain]
                else:
                    # Keep unknown domains but mark them
                    new_domain = domain
                
                # Create anonymized email
                email_mapping[email] = f'analyst.{email_counter}@{new_domain}'
                email_counter += 1
            
            # Replace in line
            modified_line = modified_line.replace(email, email_mapping[email])
        
        # Replace domains that might appear without email context
        for original_domain, new_domain in DOMAIN_MAP.items():
            if original_domain in modified_line:
                # Avoid double-replacing if it's already part of an email
                # Look for domain mentions that are NOT preceded by @ or @\w
                modified_line = re.sub(
                    r'(?<!@\w)' + re.escape(original_domain) + r'(?!\.)',
                    new_domain,
                    modified_line
                )
        
        anonymized_lines.append(modified_line)
    
    # Write anonymized log
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(anonymized_lines)
    
    # Print mapping statistics
    print(f"✅ Log anonymized successfully")
    print(f"   Email mappings: {len(email_mapping)}")
    print(f"   Domain mappings: {len([d for d in DOMAIN_MAP if any(d in line for line in lines)])}")
    print()
    print("Email mappings created:")
    for original, anon in sorted(email_mapping.items()):
        print(f"  {original:40} → {anon}")
    print()
    print(f"Output: {output_file}")

if __name__ == '__main__':
    input_log = Path('/home/user/Documents/MyGithub/AIPA/SuperAgent/logs/superagent.log')
    output_log = Path('/home/user/Documents/MyGithub/AIPA/SuperAgent/logs/superagent_anonymized.log')
    
    if not input_log.exists():
        print(f"❌ File not found: {input_log}")
        sys.exit(1)
    
    anonymize_log(str(input_log), str(output_log))
