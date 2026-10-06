from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


st.set_page_config(page_title="Airbnb Rio | Observatorio", layout="wide")


@st.cache_data
def carregar_dados():
    caminho_csv = Path(__file__).with_name("listings.csv")
    dados = pd.read_csv(caminho_csv)
    dados["neighbourhood"] = dados["neighbourhood"].fillna("Bairro não informado")
    return dados


df = carregar_dados()
precos_validos = df.loc[df["price"].gt(0), "price"].dropna()
limite_p95 = int(precos_validos.quantile(0.95))
bairros_top10 = df["neighbourhood"].value_counts().head(10).index.tolist()
tipos = sorted(df["room_type"].dropna().unique().tolist())

st.title("Airbnb no Rio de Janeiro")
st.caption("Anúncios ativos coletados em 24/06/2026 | Inside Airbnb")

with st.sidebar:
    st.header("Filtros")
    bairros = st.multiselect("Bairros", bairros_top10, default=bairros_top10)
    tipos_selecionados = st.multiselect("Tipos de acomodação", tipos, default=tipos)
    preco_maximo = st.slider(
        "Preço máximo exibido (R$)",
        min_value=int(precos_validos.min()),
        max_value=limite_p95,
        value=limite_p95,
        step=1,
    )

base = df.loc[
    df["neighbourhood"].isin(bairros)
    & df["room_type"].isin(tipos_selecionados)
].copy()
precos = base.loc[
    base["price"].gt(0) & base["price"].le(preco_maximo)
].copy()

if base.empty:
    st.warning("A seleção não contém anúncios. Ajuste os filtros.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Anúncios nos bairros/tipos", f"{len(base):,}".replace(",", "."))
col2.metric(
    "Mediana de preço no recorte",
    f"R$ {precos['price'].median():,.0f}" if not precos.empty else "Sem preço",
)
col3.metric(
    "Mediana de disponibilidade declarada",
    f"{base['availability_365'].median():.0f} dias",
)

st.subheader("Preço por bairro: observado vs padronizado")
if precos.empty:
    st.info("Não há preços positivos no recorte atual.")
elif len(bairros) < 2:
    st.info("Selecione pelo menos dois bairros para comparar a composição.")
else:
    contagem_tipos = (
        precos.groupby(["neighbourhood", "room_type"])["price"]
        .size()
        .unstack(fill_value=0)
        .reindex(index=bairros, fill_value=0)
    )
    tipos_comuns = [
        tipo for tipo in contagem_tipos.columns
        if contagem_tipos[tipo].ge(20).all()
    ]
    if len(tipos_comuns) < 2:
        st.info("São necessários dois tipos com pelo menos 20 preços em cada bairro selecionado.")
    else:
        comparaveis = precos.loc[precos["room_type"].isin(tipos_comuns)].copy()
        pesos_tipo = comparaveis["room_type"].value_counts(normalize=True).reindex(tipos_comuns)
        medias_tipo = comparaveis.pivot_table(
            index="neighbourhood", columns="room_type", values="price", aggfunc="mean"
        ).reindex(index=bairros)
        media_observada = comparaveis.groupby("neighbourhood")["price"].mean().reindex(bairros)
        media_padronizada = medias_tipo[tipos_comuns].mul(pesos_tipo, axis="columns").sum(axis=1)
        comparacao = pd.DataFrame(
            {
                "neighbourhood": bairros,
                "media_observada": media_observada.to_numpy(),
                "media_padronizada": media_padronizada.to_numpy(),
                "anuncios": comparaveis.groupby("neighbourhood").size().reindex(bairros).to_numpy(),
            }
        )
        ordem_bairros = comparacao.sort_values("media_padronizada")["neighbourhood"].tolist()
        comparacao_longa = comparacao.melt(
            id_vars=["neighbourhood", "anuncios"],
            value_vars=["media_observada", "media_padronizada"],
            var_name="medida",
            value_name="preco_medio",
        )
        comparacao_longa["medida"] = comparacao_longa["medida"].map(
            {"media_observada": "Média observada", "media_padronizada": "Média padronizada"}
        )
        base_comparacao = alt.Chart(comparacao_longa).encode(
            x=alt.X("preco_medio:Q", title="Preço médio no recorte (R$)", axis=alt.Axis(format="$,.0f")),
            y=alt.Y("neighbourhood:N", title="Bairro", sort=ordem_bairros),
        )
        linhas = base_comparacao.mark_line(color="#A9B3B1", strokeWidth=2).encode(
            detail="neighbourhood:N",
            order=alt.Order("medida:N", sort="ascending"),
        )
        pontos = base_comparacao.mark_point(filled=True, size=95).encode(
            color=alt.Color(
                "medida:N",
                title="Medida",
                scale=alt.Scale(
                    domain=["Média observada", "Média padronizada"],
                    range=["#CC5A45", "#287C78"],
                ),
            ),
            tooltip=[
                alt.Tooltip("neighbourhood:N", title="Bairro"),
                alt.Tooltip("medida:N", title="Medida"),
                alt.Tooltip("preco_medio:Q", title="Preço médio (R$)", format=",.2f"),
                alt.Tooltip("anuncios:Q", title="Anúncios comparáveis", format=","),
            ],
        )
        st.altair_chart(
            (linhas + pontos).properties(
                title="Preço antes e depois de padronizar o tipo de hospedagem", height=330
            ),
            width="stretch",
        )

st.subheader("Mediana de preço por bairro e tipo")
resumo_preco = (
    precos.groupby(["neighbourhood", "room_type"], as_index=False)
    .agg(mediana_preco=("price", "median"), anuncios=("price", "size"))
)
resumo_preco = resumo_preco.loc[resumo_preco["anuncios"].ge(20)]
if resumo_preco.empty:
    st.info("Nenhuma combinação tem pelo menos 20 preços válidos.")
else:
    grafico_mapa = (
        alt.Chart(resumo_preco)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("room_type:N", title="Tipo de acomodação"),
            y=alt.Y("neighbourhood:N", title="Bairro", sort=bairros),
            color=alt.Color(
                "mediana_preco:Q",
                title="Mediana (R$)",
                scale=alt.Scale(scheme="tealblues"),
            ),
            tooltip=[
                alt.Tooltip("neighbourhood:N", title="Bairro"),
                alt.Tooltip("room_type:N", title="Tipo"),
                alt.Tooltip("mediana_preco:Q", title="Mediana (R$)", format=",.2f"),
                alt.Tooltip("anuncios:Q", title="Anúncios", format=","),
            ],
        )
        .properties(title="Combinações com pelo menos 20 anúncios", height=330)
    )
    st.altair_chart(grafico_mapa, width="stretch")

st.subheader("Volume de anúncios por bairro e tipo")
contagem = (
    base.groupby(["neighbourhood", "room_type"], as_index=False)
    .size()
    .rename(columns={"size": "anuncios"})
)
grafico_volume = (
    alt.Chart(contagem)
    .mark_bar()
    .encode(
        x=alt.X("anuncios:Q", title="Número de anúncios"),
        y=alt.Y("neighbourhood:N", title="Bairro", sort=bairros),
        color=alt.Color(
            "room_type:N",
            title="Tipo de acomodação",
            scale=alt.Scale(scheme="tableau10"),
        ),
        tooltip=[
            alt.Tooltip("neighbourhood:N", title="Bairro"),
            alt.Tooltip("room_type:N", title="Tipo"),
            alt.Tooltip("anuncios:Q", title="Anúncios", format=","),
        ],
    )
    .properties(title="Oferta ativa na seleção atual", height=330)
)
st.altair_chart(grafico_volume, width="stretch")

st.subheader("Disponibilidade anunciada")
resumo_disponibilidade = (
    base.groupby("neighbourhood", as_index=False)
    .agg(mediana_dias=("availability_365", "median"), anuncios=("id", "size"))
    .sort_values("mediana_dias")
)
grafico_disponibilidade = (
    alt.Chart(resumo_disponibilidade)
    .mark_bar(color="#287C78")
    .encode(
        x=alt.X(
            "mediana_dias:Q",
            title="Mediana de dias disponíveis (0–365)",
            scale=alt.Scale(domain=[0, 365]),
        ),
        y=alt.Y("neighbourhood:N", title="Bairro", sort="-x"),
        tooltip=[
            alt.Tooltip("neighbourhood:N", title="Bairro"),
            alt.Tooltip("mediana_dias:Q", title="Mediana (dias)", format=".0f"),
            alt.Tooltip("anuncios:Q", title="Anúncios", format=","),
        ],
    )
    .properties(title="Dias declarados disponíveis por bairro", height=330)
)
st.altair_chart(grafico_disponibilidade, width="stretch")

st.caption(
    "Disponibilidade é a declarada no calendário, não ocupação observada. "
    "Preços ausentes não entram nos gráficos de preço; o limite inicial é o p95 global."
)
