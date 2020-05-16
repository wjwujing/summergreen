# -*- coding: utf-8 -*-
# Author: Steven Field

import cudf
import datetime
import pandas as pd
from queue import Queue
import threading
cudf.set_allocator("managed")


class StockMerger(object):
    def __init__(self, trade_date):
        self.trade_date = trade_date
        self.is_trading = True
        self.cut_off_time = self.trade_date
        self.shift_timedelta = datetime.timedelta(seconds=15)
        self.ordered_columns = [
            "current", "high", "low", "volume", "money",
            "a1_p", "a2_p", "a3_p", "a4_p", "a5_p", "a1_v", "a2_v", "a3_v", "a4_v", "a5_v",
            "b1_p", "b2_p", "b3_p", "b4_p", "b5_p", "b1_v", "b2_v", "b3_v", "b4_v", "b5_v",
        ]
        self.ordered_index = ['code', 'time']
        self.persistent_cdf = cudf.DataFrame(columns=self.ordered_index + self.ordered_columns)
        self.persistent_cdf = self.persistent_cdf.set_index(self.ordered_index)
        self.tmp_df = pd.DataFrame(columns=self.ordered_columns)
        self.stock_queue = Queue()
        # self.tmp_merge_threader = threading.Thread(target=self.stock_dict2tmp_dict, daemon=True)
        # self.tmp_merge_threader.start()

    def estimate_trading(self, stock_dict):
        trade_date_list = list(set([i[1].date() for i in stock_dict.keys()]))
        if self.trade_date.date() not in trade_date_list:
            self.is_trading = False

    def cache_stock_dict(self, stock_dict):
        self.stock_queue.put(stock_dict)

    def stock_dict2tmp_dict(self):
        while True:
            try:
                stock_df_list = [self.tmp_df, pd.DataFrame.from_dict(self.stock_queue.get(), orient='index')]
                tmp_df = pd.concat(stock_df_list)
                tmp_df = tmp_df[tmp_df.index.map(lambda x: x[1] >= self.cut_off_time)]
                tmp_df = tmp_df.loc[~tmp_df.index.duplicated(keep='first')]
                tmp_df.index = pd.MultiIndex.from_tuples(tmp_df.index)
                self.tmp_df = tmp_df
                self.stock_queue.task_done()
            except Exception as e:
                print(e)

    def tmp2persistent_delayed(self):
        tmp_df = self.tmp_df.copy()
        cut_off_time = tmp_df.index.map(lambda x: x[1]).max() - self.shift_timedelta
        tmp_df = tmp_df[tmp_df.index.map(lambda x: x[1] < cut_off_time)]
        tmp_cdf = cudf.from_pandas(tmp_df)
        self.persistent_cdf = cudf.concat([self.persistent_cdf, tmp_cdf])
        self.cut_off_time = cut_off_time

    def tmp2persistent(self):
        tmp_cdf = cudf.from_pandas(self.tmp_df)
        self.persistent_cdf = cudf.concat([self.persistent_cdf, tmp_cdf])
        self.tmp_df = pd.DataFrame(columns=self.ordered_columns)

    def save_persistent2parquet(self, parquet_path):
        self.persistent_cdf.to_parquet(parquet_path)
