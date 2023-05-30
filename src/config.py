import configparser

class Config:
    def __init__(self, filepath: str = "config.ini"):
        parser = configparser.ConfigParser()
        parser.read(filepath)
        
        # weights
        header_weight: float = float(parser["WEIGHTS"]["HEADER"])
        bold_weight: float = float(parser["WEIGHTS"]["BOLD"])
        title_weight: float = float(parser["WEIGHTS"]["TITLE"])
        cosine_similarity_weight: float = float(parser["WEIGHTS"]["COSINE_SIMILARITY"])
        # self.alpha: float = float(parser["WEIGHTS"]["ALPHA"])
        
        # general options
        self.sim_thresh: float = float(parser["GENERAL"]["SIM_THRESH"])
        """Threshold for similarity detection."""
        self.k_results: int = int(parser["GENERAL"]["KRESULTS"])
        """Number of results to return."""
        self.r_docs: int = int(parser["GENERAL"]["RDOCS"])
        """Number of posts to traverse per term. Value < 0 indicates no limit."""
        
        # normalize weights
        total = header_weight + bold_weight + title_weight + cosine_similarity_weight
        self.header_weight = header_weight / total
        self.bold_weight = bold_weight / total
        self.title_weight = title_weight / total
        self.cosine_similarity_weight = cosine_similarity_weight / total