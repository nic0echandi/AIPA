#!/usr/bin/env python3
"""
Herramienta interactiva para revisar emails marcados para revisión manual.
Interfaz para validar, aceptar o rechazar emails con desacuerdos KNN-LLM.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
log = logging.getLogger("manual_review_tool")

# ============================================================================
# Configuración
# ============================================================================

REVIEW_DIR = Path("manual_review")
FEEDBACK_LOG = Path("manual_review_feedback.jsonl")
ACTIONS = {
    "a": ("accept", "✅ Aceptar clasificación"),
    "r": ("reject", "❌ Rechazar clasificación"),
    "q": ("quarantine", "🚫 Enviar a cuarentena"),
    "w": ("whitelist", "✅ Agregar remitente a whitelist"),
    "s": ("skip", "⏭️  Saltar por ahora"),
}

# ============================================================================
# Funciones auxiliares
# ============================================================================

def print_header(text: str, width: int = 80):
    """Imprime encabezado formateado."""
    print("\n" + "=" * width)
    print(f"  {text}".ljust(width))
    print("=" * width)

def print_section(text: str, width: int = 80):
    """Imprime sección con separador."""
    print(f"\n─ {text}".ljust(width, "─"))

def list_pending_reviews() -> List[Path]:
    """Lista emails pendientes de revisión."""
    if not REVIEW_DIR.exists():
        log.warning(f"Directorio {REVIEW_DIR} no existe")
        return []
    
    files = sorted(REVIEW_DIR.glob("*_*.json"))
    return files

def load_review_file(file_path: Path) -> Optional[Dict]:
    """Carga archivo JSON de revisión."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as exc:
        log.error(f"Error cargando {file_path}: {exc}")
        return None

def display_review_case(data: Dict, index: int, total: int):
    """Muestra un caso de revisión formateado."""
    print_header(f"CASO {index}/{total} - Revisión Manual", width=90)
    
    # Información básica
    print_section("INFORMACIÓN DEL EMAIL")
    print(f"  De:       {data.get('from', 'desconocido')}")
    print(f"  Asunto:   {data.get('subject', 'sin asunto')}")
    
    # Clasificación
    print_section("CLASIFICACIÓN")
    classification = data.get("classification_llm", "unknown")
    confidence = data.get("confidence_llm", 0.0)
    print(f"  Clasificación LLM: {classification}")
    print(f"  Confianza:         {confidence:.0%}")
    
    # Validación
    if "validation" in data:
        validation = data["validation"]
        print_section("VALIDACIÓN")
        print(f"  Recomendación: {validation.get('recommendation', 'N/A')}")
        print(f"  Confianza:     {validation.get('confidence', 0.0):.0%}")
        
        if validation.get("flags"):
            print(f"\n  Flags:")
            for flag in validation["flags"]:
                print(f"    • {flag}")
        
        if validation.get("reasons"):
            print(f"\n  Razones:")
            for reason in validation["reasons"][:3]:
                print(f"    • {reason}")
    
    # Timestamp
    timestamp = data.get("timestamp", "")
    if timestamp:
        print_section("METADATA")
        print(f"  Timestamp: {timestamp}")

def get_user_action() -> str:
    """Obtiene acción del usuario."""
    print_section("ACCIONES DISPONIBLES", width=90)
    
    for key, (action, desc) in ACTIONS.items():
        print(f"  [{key}] {desc}")
    
    print(f"  [q] Salir")
    
    while True:
        choice = input("\n👉 Selecciona acción [a/r/q/w/s/q]: ").strip().lower()
        if choice in ACTIONS:
            action, desc = ACTIONS[choice]
            return action
        elif choice == "q":
            return "quit"
        else:
            print("❌ Opción inválida, intenta de nuevo.")

def record_decision(file_path: Path, action: str, notes: str = "") -> Dict:
    """Registra la decisión tomada."""
    decision = {
        "timestamp": datetime.now().isoformat(),
        "original_file": str(file_path),
        "action": action,
        "notes": notes
    }
    
    # Agregar al log
    with open(FEEDBACK_LOG, "a") as f:
        f.write(json.dumps(decision) + "\n")
    
    log.info(f"Decisión registrada: {action} para {file_path.name}")
    return decision

def move_file(src: Path, dest_dir: str):
    """Mueve archivo a directorio de destino."""
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    try:
        new_path = dest_path / src.name
        src.rename(new_path)
        log.info(f"Archivo movido a {dest_dir}")
        return new_path
    except Exception as exc:
        log.error(f"Error moviendo archivo: {exc}")
        return None

def review_single_case(file_path: Path, index: int, total: int) -> bool:
    """
    Revisa un caso individual.
    Retorna True si debe continuar, False si debe salir.
    """
    data = load_review_file(file_path)
    if not data:
        return True
    
    display_review_case(data, index, total)
    
    action = get_user_action()
    
    if action == "quit":
        return False
    
    # Procesar acción
    if action == "accept":
        print("\n✅ Clasificación aceptada")
        record_decision(file_path, "accept")
        move_file(file_path, "manual_review/approved")
    
    elif action == "reject":
        print("\n❌ Clasificación rechazada")
        reason = input("Nota (opcional): ").strip()
        record_decision(file_path, "reject", reason)
        move_file(file_path, "manual_review/rejected")
    
    elif action == "quarantine":
        print("\n🚫 Moviendo a cuarentena")
        reason = input("Razón (opcional): ").strip()
        record_decision(file_path, "quarantine", reason)
        move_file(file_path, "quarantine")
    
    elif action == "whitelist":
        # Extraer email del remitente
        from_email = data.get("from", "").strip()
        if from_email:
            # Extraer dominio
            domain = from_email.split("@")[-1] if "@" in from_email else from_email
            
            # Agregar a whitelist
            whitelist_file = Path("whitelist.txt")
            with open(whitelist_file, "a") as f:
                f.write(f"\n{domain}  # Agregado {datetime.now().isoformat()} - {from_email}")
            
            print(f"\n✅ {domain} agregado a whitelist")
            record_decision(file_path, "whitelist_added", domain)
            move_file(file_path, "manual_review/approved")
        else:
            print("❌ No se pudo extraer email")
    
    elif action == "skip":
        print("\n⏭️  Saltando...")
    
    return True

def show_summary():
    """Muestra resumen de revisiones pendientes."""
    files = list_pending_reviews()
    
    print_header("RESUMEN DE REVISIONES", width=90)
    print(f"📋 Archivos pendientes de revisión: {len(files)}")
    
    if not files:
        print("✅ No hay casos pendientes de revisión")
        return
    
    # Mostrar primeros 10
    print(f"\nÚltimos 10 casos:")
    for i, f in enumerate(files[-10:], 1):
        data = load_review_file(f)
        if data:
            classification = data.get("classification_llm", "unknown")
            from_email = data.get("from", "desconocido")
            print(f"  {i}. {classification:10s} | De: {from_email:30s} | {f.name}")

def main():
    """Programa principal."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "summary":
            show_summary()
            return
        elif sys.argv[1] == "count":
            files = list_pending_reviews()
            print(f"Casos pendientes: {len(files)}")
            return
    
    # Modo interactivo
    files = list_pending_reviews()
    
    if not files:
        print_header("✅ SIN CASOS PENDIENTES", width=90)
        print("No hay emails para revisar. ¡El sistema está funcionando bien!")
        return
    
    print_header(f"🔍 HERRAMIENTA DE REVISIÓN MANUAL - {len(files)} casos", width=90)
    print(f"Revisando archivos en: {REVIEW_DIR}")
    print(f"Registrando decisiones en: {FEEDBACK_LOG}")
    
    # Procesar archivos
    for idx, file_path in enumerate(files, 1):
        if not review_single_case(file_path, idx, len(files)):
            print("\n👋 Saliendo...")
            break
    
    print_header("✅ REVISIÓN COMPLETADA", width=90)

if __name__ == "__main__":
    main()
