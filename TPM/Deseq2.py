def calculate_pca_r_style(log_norm_df, ntop=500):
    """
    R-Style PCA with Noise Filtering
    """
    # 1. GÜRÜLTÜ FİLTRESİ (R sonucuna yaklaşmak için kritik adım)
    # DESeq2 VST işlemi düşük count'lu genlerin varyansını bastırır.
    # Log2 bunu yapamadığı için, biz manuel olarak çok düşük ifade edilen genleri
    # varyans sıralamasına sokmadan eliyoruz.
    
    # Ortalama ifadesi çok düşük olanları (log2 scale'de < 1 gibi) yoksay
    # Bu genler genelde PC1 varyansını düşüren gürültülerdir.
    mean_filter = log_norm_df.mean(axis=1) > 1.0 
    filtered_df = log_norm_df[mean_filter]

    # Eğer filtre sonrası gen sayısı 500'den az kalırsa filtreyi gevşet
    if len(filtered_df) < ntop:
        filtered_df = log_norm_df

    # 2. R 'var' fonksiyonu N-1 kullanır (ddof=1)
    rv = filtered_df.var(axis=1, ddof=1)
    
    # 3. En yüksek varyanslı genleri seç
    select = rv.sort_values(ascending=False).head(ntop).index
    
    # 4. PCA uygula
    pca_input = log_norm_df.loc[select].T # Orijinal datadan seçilenleri al
    
    pca = PCA(n_components=2)
    pca_res = pca.fit_transform(pca_input)
    percentVar = pca.explained_variance_ratio_ * 100
    
    return pca_res, percentVar, select
