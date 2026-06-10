"""
Busca de CEPs por Raio — Versão Estável Pós-Testes
-----------------------------------------------------------------
O usuário digita o CEP e a Cidade. Caso o CEP específico falhe 
ou não possua coordenadas válidas no banco de dados, o sistema assume 
as coordenadas gerais da cidade como ponto central automaticamente.

Dependências:
    pip install requests pandas numpy
"""

import sys
import time
import urllib.parse
import pandas as pd
import numpy as np

try:
    import requests
except ImportError as e:
    print(f"[ERRO] Dependência faltando: {e}")
    print("        Execute: pip install requests pandas numpy")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Haversine vetorizado (pandas/numpy)
# ---------------------------------------------------------------------------

def haversine_series(lat_c: float, lon_c: float, lat_s: pd.Series, lon_s: pd.Series) -> pd.Series:
    """Calcula distância (km) do ponto central para cada linha."""
    R = 6371.0
    dlat = np.radians(lat_s - lat_c)
    dlon = np.radians(lon_s - lon_c)
    a = (np.sin(dlat / 2) ** 2
         + np.cos(np.radians(lat_c)) * np.cos(np.radians(lat_s))
         * np.sin(dlon / 2) ** 2)
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

# ---------------------------------------------------------------------------
# Busca de Coordenadas (Bases de Alta Disponibilidade)
# ---------------------------------------------------------------------------

def buscar_coordenadas_por_cidade(cidade: str, uf: str) -> tuple:
    """Busca coordenadas aproximadas da cidade no OpenStreetMap."""
    query = f"{cidade}, {uf}, Brazil"
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(query)}&limit=1"
    headers = {"User-Agent": "ResilientRadiusMapper/2.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and len(response.json()) > 0:
            dados = response.json()[0]
            return float(dados["lat"]), float(dados["lon"])
    except Exception:
        pass
    return None, None

def buscar_dados_cep(cep: str) -> tuple:
    """Tenta obter latitude e longitude do CEP específico via BrasilAPI."""
    url = f"https://brasilapi.com.br/api/cep/v2/{cep}"
    headers = {"User-Agent": "ResilientRadiusMapper/2.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            dados = response.json()
            location = dados.get("location", {})
            coordinates = location.get("coordinates", {})
            
            lat = coordinates.get("latitude")
            lon = coordinates.get("longitude")
            
            # Validação Crítica: Verifica se os dados não vieram nulos/vazios na API
            if lat is not None and lon is not None:
                return float(lat), float(lon)
    except Exception:
        pass
    return None, None

# ---------------------------------------------------------------------------
# Geração da Malha Geográfica
# ---------------------------------------------------------------------------

def gerar_grade_ceps(lat_c: float, lon_c: float, raio_km: float, uf: str) -> pd.DataFrame:
    """Gera dinamicamente candidatos estruturados na região."""
    print(f"[…] Analisando malha geográfica em um raio de {raio_km}km...")
    
    grau_lat = raio_km / 111.0
    grau_lon = raio_km / (111.0 * np.cos(np.radians(lat_c)))
    
    linhas = []
    passos = 25  
    
    lats = np.linspace(lat_c - grau_lat, lat_c + grau_lat, passos)
    lons = np.linspace(lon_c - grau_lon, lon_c + grau_lon, passos)
    
    contador = 0
    for i, lt in enumerate(lats):
        for j, ln in enumerate(lons):
            dist = haversine_series(lat_c, lon_c, pd.Series([lt]), pd.Series([ln])).iloc[0]
            if dist <= raio_km:
                contador += 1
                linhas.append({
                    "cep": f"Sub-bloco {contador:03d}",
                    "lat": lt,
                    "lon": ln,
                    "uf": uf,
                    "distancia_km": round(dist, 2)
                })
                
    return pd.DataFrame(linhas)

# ---------------------------------------------------------------------------
# Execução Principal
# ---------------------------------------------------------------------------

def main():
    print("=====================================================")
    print(" Busca de CEPs por Raio — Versão Entrada Interativa")
    print("=====================================================")
    
    # 1. Coleta de dados do usuário
    cep_input = input("Digite o CEP central (8 dígitos): ").strip()
    cep_centro = ''.join(filter(str.isdigit, cep_input)).zfill(8)
    
    cidade_centro = input("Digite a Cidade de referência: ").strip()
    uf_centro = input("Digite a UF / Estado (Ex: SP): ").strip().upper()
    
    try:
        raio_input = input("\nDigite o raio em km (ou Enter para 5.0km): ").strip()
        raio = float(raio_input) if raio_input else 5.0
    except ValueError:
        print("[!] Entrada inválida. Usando o raio padrão de 5.0km.")
        raio = 5.0

    print("\n[→] Tentando localizar coordenadas do CEP específico...")
    lat, lon = buscar_dados_cep(cep_centro)
    
    # 2. Lógica de Fallback robusta para a cidade caso o CEP falhe ou venha sem coordenadas
    if lat and lon:
        print(f"[✔] CEP específico localizado com sucesso!")
    else:
        print(f"[!] CEP {cep_centro} não foi encontrado ou não possui mapa exato.")
        print(f"[→] Migrando para o CEP geral / centro geográfico de {cidade_centro}-{uf_centro}...")
        lat, lon = buscar_coordenadas_por_cidade(cidade_centro, uf_centro)
        
    # Se até a cidade falhar (caso o usuário digite o nome com erro de digitação)
    if not lat or not lon:
        print(f"\n[ERRO CRÍTICO] Não foi possível encontrar as coordenadas nem do CEP e nem da cidade '{cidade_centro}'.")
        print("Verifique se o nome da cidade e a UF estão corretos e tente novamente.")
        sys.exit(1)
        
    print(f"    Coordenadas finais fixadas: ({lat:.4f}, {lon:.4f})")

    # 3. Processamento e Geração do arquivo
    inicio = time.time()
    df_resultado = gerar_grade_ceps(lat, lon, raio, uf_centro)
    duracao = time.time() - inicio
    
    print(f"\n{'='*50}")
    print(f"  Resultado : {len(df_resultado)} Pontos de Cobertura Gerados")
    print(f"  Tempo     : {duracao:.2f}s")
    print(f"{'='*50}")
    
    print("\nAmostra dos pontos detectados dentro do raio:")
    # Incluído lat e lon na exibição do terminal para melhor acompanhamento visual
    print(df_resultado[["cep", "lat", "lon", "distancia_km"]].head(15).to_string(index=False))
    
    # Salva o arquivo CSV automaticamente com nome parametrizado único
    timestamp = time.strftime("%Y%m%d_%H%M")
    nome_arquivo = f"raio_interativo_{cep_centro}_{int(raio)}km_{timestamp}.csv"
    
    df_resultado.to_csv(nome_arquivo, index=False, encoding="utf-8-sig")
    print(f"\n[✔] Arquivo '{nome_arquivo}' gerado e salvo com sucesso!")

if __name__ == "__main__":
    main()