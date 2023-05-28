from msgspec.json import decode
from nltk.stem import SnowballStemmer
from typing import TextIO
import csv
import math
from src.helpers import tokenize
from src.config import Config

class QueryException(Exception):
    pass

IndexData = list[dict[str: int]]

class Queryier:    
    def __init__(self, indexLoc: str, cache_size: int = 25):
        """Create Queryier object to query an index.

        Args:
            indexLoc (str): the folder containing the index.
            cache_size (int, optional): how many query terms to store in the cache. Defaults to 25.

        Raises:
            QueryException: if the index is not found or if the index metadata file is missing/malformed.
        """
        # read meta data
        try:
            with open(f"{indexLoc}/meta.json", "r") as f:
                meta = decode(f.read())
            self.filename: str = meta["filename"]
            self.breakpoints: list[str] = meta["breakpoints"]
            self.documentCount: int = meta["documentCount"]
        except FileNotFoundError:
            raise QueryException(f"Index metadata file not found at: {indexLoc}")
        except KeyError:
            raise QueryException(f"Malformed metadata file at: {indexLoc}")
        
        # read meta index
        try:
            with open(f"{indexLoc}/meta_index.json", "r") as f:
                self._meta_index_ = decode(f.read())
        except FileNotFoundError:
            raise QueryException(f"Index meta_index file not found at: {indexLoc}")
        
        self.indexLoc = indexLoc
        self.pointer = 0
        self.CACHE_SIZE = cache_size
        self._cache_: list[dict[str:list[str]]] = []
        self.stemmer = SnowballStemmer("english")
        self.docs = self.getDocs()
        self._files_: list[TextIO] = [open(f"{indexLoc}/{self.filename}{i}.csv", "r") for i in range(len(self.breakpoints)+1)]
        self.config = Config()
        
        # load stopwords
        try:
            with open("stop_words.txt", "r") as f:
                self.stopwords = set(self.stemmer.stem(s) for s in f.readlines())
        except FileNotFoundError:
            raise QueryException("Stopwords file not found")
    
    def __del__(self):
        """Destructor. Closes all index files."""
        try:
            for f in self._files_:
                f.close()
        except AttributeError:
            # occurs when an error is thrown in the constructor before the _files_ attribute is created
            # caught to prevent the destructor from throwing errors
            pass
    
    def _add_cache_(self, term: str, results: list[str]) -> None:
        """Add a term and its index results to the cache, replacing the oldest cache entry if the cache is full.

        Args:
            term (str): the term to add.
            results (list[str]): the documents returned as results for that term.
        """
        if len(self._cache_) > self.CACHE_SIZE:
            self._cache_[self.pointer] = {term: results}
            self.pointer = (self.pointer + 1) % self.CACHE_SIZE
        else:
            self._cache_.append({term: results, "df": len(results)})
    
    def _check_cache_(self, term: str) -> None|tuple[int, list[str]]:
        """Check if a term is in the cache.

        Args:
            term (str): the term to search for.

        Returns:
            None|list[str]: the list of results stored in the cache. Returns None if the term was not in the cache.
        """
        for r in self._cache_:
            if term in r:
                return r["df"], r[term]
        return None
    
    def getToken(self, token: str) -> tuple[int, list[dict[str:int]]]:
        """Get the postings list for the token.

        Args:
            token (str): the token to search.

        Returns:
            list[dict[str:int]]: the postings for that token.
        """
        # position in file and file number of token
        pos, fileno = self._meta_index_[token]
        # the file containing the token
        f: TextIO = self._files_[fileno]
        # set the file pointer position
        f.seek(pos)
        # read that line
        line = f.readline()
        reader = csv.reader([line])
        line = next(reader)
        # return the decoded first r items in the line
        return int(line[1]), [decode(line[i]) for i in range(2, min(self.config.r_docs, len(line)))]
    
    def getDocs(self) -> dict[int: tuple[str, float]]:
        """Load the documents dict"""
        docs = {}
        with open(f"{self.indexLoc}/documents.csv", "r") as f:
            reader = csv.reader(f)
            for row in reader:
                docs[int(row[0])] = (row[1], float(row[2]))
        return docs

    def searchIndex(self, query: str, useStopWords: bool = False) -> list[str]:
        """Query an index.

        Args:
            query (str): the query to search for.
            useStopWords (str, optional): whether to include stopwords in the searched-for terms. Defaults to False.

        Returns:
            list[str]: a list of document names that matched the query.
        """
        
        results: dict[str: list[dict[str: int]]] = {}
        scores: list[float] = []
        docIDs = {}
        queryDF: dict[str: float] = {}
        
        # stem query tokens
        terms = [self.stemmer.stem(w) for w in tokenize(query)]
        if not useStopWords:
            tempL = len(terms)
            terms = [w for w in terms if w not in self.stopwords]
            removedStopWords = len(terms) < tempL
        # for each token in the query
        for term in terms:
            # check cache
            cacheResult = self._check_cache_(term)
            if cacheResult is not None:
                queryDF[term] = cacheResult[0]
                results[term] = cacheResult[1]
                continue
            try:
                df, res = self.getToken(term)
                queryDF[term] = df
                results[term] = res
                # add to cache
                self._add_cache_(term, res)
            except KeyError:
                # if the term is not found in the index
                # currently ignores this failure
                continue
        
        # calculate all query term weights
        queryDF = {term: (1 + math.log10(terms.count(term))) * math.log10(self.documentCount / queryDF[term]) for term in terms}
        queryLength = math.sqrt(sum(v**2 for v in queryDF.values()))
        
        for term in terms:
            # calculate w-tq
            wtq = queryDF[term] / queryLength
            # add score for this term in each doc to the running sum
            for post in results[term]:
                id = post["id"]
                tf = post["frequency"]
                if id not in docIDs:
                    docIDs[id] = len(docIDs)
                    scores.append(0)
                scores[docIDs[id]] += wtq * tf
        
        # calculate final cosine similarity scores
        for d,i in docIDs.items():
            scores[i] /= self.docs[d][1]
        
        # TODO: Add more scoring methods
        
        # divide by normalized document length and retrieve documents in rank order
        ranked = sorted(((d, scores[i]) for d,i in docIDs.items()), key = lambda x: x[1], reverse = True)
        
        # redo using stopwords if not enough results
        if len(ranked) < self.config.k_results and not useStopWords and removedStopWords:
            return self.searchIndex(query, True)
        
        # convert to urls
        urls = [self.docs[d][0] for d,_ in ranked[:self.config.k_results]]

        # return top k results
        return urls