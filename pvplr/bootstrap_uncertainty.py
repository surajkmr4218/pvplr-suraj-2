from pvplr.feature_correction import PLRProcessor
from pvplr.model_comparison import PLRModel
from pvplr.plr_determination import PLRDetermination
import matplotlib.pyplot as plt
from scipy.stats import t
import pandas as pd
import numpy as np

# Creat Processing OBject -------------------------------------------------------
processor = PLRProcessor()

# Create Comparison Object ------------------------------------------------------
model_comparison = PLRModel()

# Create PLR Determination Object -----------------------------------------------
determination = PLRDetermination()

class PLRBootstrap:

    def __init__(self):
        pass

    # Helper function that returns proper per_year number
    def get_per_year(self, by):
        if by == "day":
            return 365
        elif by == "week":
            return 52
        elif by == "month":
            return 12
        else:
            return 0  # Catches Errors

    # Helper function that returns dataframe after raw data goes through the correct model
    def pick_model(self, model, df, var_list, by, data_cutoff, pred, nameplate_power):
            if model == "xbx":
                res = model_comparison.plr_xbx_model(df, var_list=var_list, by=by, data_cutoff=data_cutoff, predict_data=pred)
            elif model == "correction":
                res = model_comparison.plr_xbx_utc_model(df, var_list=var_list, by=by, data_cutoff=data_cutoff, predict_data=pred)
            elif model == "pvusa":
                res = model_comparison.plr_pvusa_model(df, var_list=var_list, by=by, data_cutoff=data_cutoff, predict_data=pred)
            elif model == "6k":
                res = model_comparison.plr_6k_model(df, var_list=var_list, by=by, data_cutoff=data_cutoff, nameplate_power=nameplate_power, predict_data=pred)
            else:
                raise ValueError("Error: model not recognized. See method documentation for plr_bootstrap_uncertainty")
            
            return res

    # Helper function that returns random fraction sample of data
    def mbm_resample(self, df, fraction, by):
        if by == "month":
            groupby_var = 'psem'
        elif by == "week":
            groupby_var = 'week'
        elif by == "day":
            groupby_var = 'day'
        else:
            raise ValueError("Invalid 'by' parameter. Must be 'month', 'week', or 'day'.")
        
        groups = df[groupby_var].unique()
        resampled_dfs = []

        for group in groups:

            group_df = df[df[groupby_var] == group]
            # Get the total number of rows
            total_rows = len(group_df)
            # Create a list of all rows indices
            all_rows = list(range(total_rows))
            
            # Calculate the number of rows for each dataset split
            train_rows_count = int(total_rows * fraction)

            np.random.shuffle(all_rows)
            
            # Split the shuffled list of row indices into training, testing, and validation sets
            train_rows_indices = all_rows[:train_rows_count]
            sample = group_df.iloc[train_rows_indices, :]
            resampled_dfs.append(sample)
        
        re = pd.concat(resampled_dfs, ignore_index=True)
        
        return re
            
    # Bootstraps raw data and puts it through modeling and PLR determination
    def plr_bootstrap_uncertainty(self, df, n, fraction, var_list, model, by, power_var, time_var, data_cutoff, nameplate_power, pred):
        per_year = self.get_per_year(by)
        
        roc_df = pd.DataFrame(columns=['reg', 'yoy'])
        for i in range(n):
            df_sub = self.mbm_resample(df=df, fraction=fraction, by=by)
            res = self.pick_model(model=model, df=df_sub, var_list=var_list, by=by, data_cutoff=data_cutoff, pred=pred, nameplate_power=nameplate_power)

            if model == '6k':
                res['weight'] = 1
            else:
                res['weight'] = 1 / (res['sigma']) ** 2
            
            roc_reg = determination.plr_weighted_regression(data=res, power_var=power_var, time_var=time_var, model=model, per_year=per_year, weight_var="weight")
            roc_yoy = determination.plr_yoy_regression(data=res, power_var=power_var, time_var=time_var, model=model, per_year=per_year, return_PLR=True)
            
            rr = pd.DataFrame({
                'reg': [roc_reg['plr'].values[0]],
                'yoy': [roc_yoy['plr'].values[0]],
            })
            roc_df = pd.concat([roc_df, rr], ignore_index=True)
            roc_df.dropna(how='all')
        
        result = pd.DataFrame({
            'plr': [roc_df['reg'].mean(), roc_df['yoy'].mean()],
            'error_95_conf': [
                t.ppf(0.975, n - 1) * roc_df['reg'].std() / np.sqrt(n),
                t.ppf(0.975, n - 1) * roc_df['yoy'].std() / np.sqrt(n)
            ],
            'error_std_dev': [roc_df['reg'].std(), roc_df['yoy'].std()],
            'method': ['weighted', 'YoY'], 
            'model': [model, model],
        })
        
        return result

    # First puts raw data through modeling and bootstraps that data
    def plr_bootstrap_output(self, df, n, fraction, var_list, model, by, power_var, time_var, data_cutoff, nameplate_power, pred):
        mod_res = self.pick_model(model=model, df=df, var_list=var_list, by=by, data_cutoff=data_cutoff, pred=pred, nameplate_power=nameplate_power)

        if model == '6k':
            mod_res['sigma'] = 1
        mod_res['weight'] = 1/mod_res['sigma']
        total_rows = len(mod_res)

        per_year = self.get_per_year(by)

        res = pd.DataFrame(columns=['reg', 'yoy'])
        for i in range(n):
            all_rows = list(range(total_rows))
            train_rows_count = int(total_rows * fraction)
            np.random.shuffle(all_rows)
            train_rows_indices = all_rows[:train_rows_count]
            re = mod_res.iloc[train_rows_indices, :]
            roc_reg = determination.plr_weighted_regression(data=re, power_var=power_var, time_var=time_var, model=model, per_year=per_year, weight_var="weight")
            roc_yoy = determination.plr_yoy_regression(data=re, power_var=power_var, time_var=time_var, model=model, per_year=per_year, return_PLR=True)
            iter_data = pd.DataFrame({
                'reg': [roc_reg['plr'].values[0]],
                'yoy': [roc_yoy['plr'].values[0]]
            })
            res = pd.concat([res, iter_data], ignore_index=True)
            res.dropna()
        
        fin = pd.DataFrame({
            'plr': [res['reg'].mean(), res['yoy'].mean()],
            'error_95_conf': [
                t.ppf(0.975, n - 1) * res['reg'].std() / np.sqrt(n),
                t.ppf(0.975, n - 1) * res['yoy'].std() / np.sqrt(n)
            ],
            'error_std_dev': [res['reg'].std(), res['yoy'].std()],
            'method': ['regression', 'YoY'],
            'model': [model, model]
        })

        return fin

    # Bootstraps the result after data went through power models
    # Inputted dataframe should be the one after passing through the model
    def plr_bootstrap_output_from_results(self, df, n, fraction, model, by, power_var, time_var, weight_var):
        per_year = self.get_per_year(by)

        res = pd.DataFrame(columns=['reg', 'yoy'])
        total_rows = len(df)
        for i in range(n):
            all_rows = list(range(total_rows))
            train_rows_count = int(total_rows * fraction)
            np.random.shuffle(all_rows)
            train_rows_indices = all_rows[:train_rows_count]
            re = df.iloc[train_rows_indices, :]
            roc_reg = determination.plr_weighted_regression(data=re, power_var=power_var, time_var=time_var, model=model, per_year=per_year, weight_var=weight_var)
            roc_yoy = determination.plr_yoy_regression(data=re, power_var=power_var, time_var=time_var, model=model, per_year=per_year, return_PLR=True)
            iter_data = pd.DataFrame({
                'reg': [roc_reg['plr'].values[0]],
                'yoy': [roc_yoy['plr'].values[0]]
            })
            res = pd.concat([res, iter_data], ignore_index=True)
            res.dropna()

        fin = pd.DataFrame({
            'plr': [res['reg'].mean(), res['yoy'].mean()],
            'error_95_conf': [
                t.ppf(0.975, n - 1) * res['reg'].std() / np.sqrt(n),
                t.ppf(0.975, n - 1) * res['yoy'].std() / np.sqrt(n)
            ],
            'error_std_dev': [res['reg'].std(), res['yoy'].std()],
            'method': ['regression', 'YoY'],
            'model': [model, model]
        })

        return fin


