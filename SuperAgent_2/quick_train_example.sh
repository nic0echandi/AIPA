#!/bin/bash
# quick_train_example.sh - Ejemplo rápido de cómo entrenar el KNN

echo "🎓 Ejemplo de Entrenamiento del KNN"
echo "==================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "superagent_2.py" ]; then
    echo "❌ Error: ejecutar desde directorio SuperAgent_2/"
    exit 1
fi

# 1. Verificar que hay emails de entrenamiento
if [ ! -d "test_emails" ] || [ -z "$(ls test_emails/*.txt 2>/dev/null)" ]; then
    echo "⚠️  No hay emails en test_emails/"
    echo ""
    echo "Para entrenar necesitas:"
    echo "1. Copiar emails de entrenamiento:"
    echo "   cp samples/*.txt test_emails/"
    echo ""
    echo "2. O crear emails de prueba manualmente"
    exit 0
fi

echo "✓ Directorio test_emails/ encontrado"
email_count=$(ls test_emails/*.txt 2>/dev/null | wc -l)
echo "✓ Emails encontrados: $email_count"
echo ""

# 2. Mostrar opciones
echo "Opciones de entrenamiento:"
echo ""
echo "  A) Testing sin entrenar (seguro, validar primero):"
echo "     python test_superagent.py --mode full"
echo ""
echo "  B) Entrenar el KNN (actualizar modelo):"
echo "     python test_superagent.py --mode train"
echo ""
echo "  C) Entrenar con debug:"
echo "     python test_superagent.py --mode train --debug"
echo ""

# 3. Preguntar si quiere ejecutar
read -p "¿Ejecutar entrenamiento? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Ejecutando: python test_superagent.py --mode train"
    echo "==================================================="
    echo ""
    python test_superagent.py --mode train
    
    echo ""
    echo "✓ Entrenamiento completado"
    echo ""
    echo "Ver resultados:"
    echo "  cat test_results/test_results.json | jq '.training'"
fi
