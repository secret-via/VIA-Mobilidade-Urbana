class ExternalTrafficProvider:
    """Contrato opcional para fontes como Waze; a visão local nunca depende dele."""
    def snapshot(self):
        return {"available": False, "source": None, "data": None}
