import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk

import os
import candas as cd
import scipy.io
import datetime

import csv
import numpy as np
from cantools.database.namedsignalvalue import NamedSignalValue
import math

script_dir = os.path.dirname(os.path.realpath(__file__))

timestep = 10  # millisecond step for interpolation (only affects CSV)


'''
Can logs in the "candas" dictionary format:

{
  "signal_1":[ [<seconds1>, <value1>], [<seconds2>, <value2>], ...],
  "signal_2":[ [<seconds1>, <value1>], [<seconds2>, <value2>], ...],
  ...
}
'''


def convert_keys_to_relative_time(data, earliest_time):
    '''Takes in candas dict and forces timestamps to be relative to first timestamp'''
    for column_header in data:
        for entry in data[column_header]:
            entry[0] = entry[0] - earliest_time
    return data


def to_float(value):
    '''Helper function to convert values to float'''
    if isinstance(value, NamedSignalValue):
        return float(value.value)
    else:
        return float(value)


def interpolate(data_dict, step_size_ms, duration, min_time):
    '''
    Function to interpolate data to X(integer) ms steps

    :param data_dict: dictionary containing dataset
    :step_size_ms: milliseconds per step you would like to interpolate the data to
    :duration: duration of dataset in seconds
    :min_time: minimum epoch of dataset

    Puts into the format:
    {
        "time": [0.0. 0.001, 0.002, ..., 0.065],
        "column_header1": [10.2, 10.2, 10.2, ..., 20.1],
        "column_header2": [30.1, 30.1, 30.1, ..., 40.5]
    }
    '''
    interpolated_data = {}
    new_time = np.arange(0, math.floor(duration), step_size_ms/1000)
    interpolated_data["Time[s]"] = new_time

    for signal, values in data_dict.items():
        # print(signal)
        old_time = np.array([to_float(item[0])
                            for item in values], dtype=np.float64)
        signal_value = np.array([to_float(item[1])
                                for item in values], dtype=np.float64)
        interpolated_data[signal] = np.interp(new_time, old_time, signal_value)

    interpolated_data["epoch"] = interpolated_data["Time[s]"] + float(min_time)

    return interpolated_data


def save_dict_to_csv(data_dict, filename):
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)

        # Write the header
        headers = list(data_dict.keys())
        writer.writerow(headers)

        # Write the rows
        rows = zip(*data_dict.values())
        for row in rows:
            writer.writerow(row)


def process_blf(input_path, output_path):
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Provide database .dbc and .ini folder location
        db = cd.load_dbc(f"{script_dir}\\put-database-here")

        # Provide file path without extension
        log_data = cd.from_file(db, input_path)
        print("ID errors are non-critical, it just means your .dbc file doesn't contain those IDs.")

        # Signals can be accessed like this
        # print(log_data["Pack_Voltage"])

        '''
        MATLAB file editing
         - Converts the times in the output .mat file to seconds since first event, not epoch
        '''
        mat = scipy.io.loadmat(f'{input_path}.mat')

        # Delete the .mat file automatically generated by candas
        os.remove(f'{input_path}.mat')

        # find start time
        min_epoch_utc = float('inf')
        max_epoch_utc = float(0)
        for key, data_points in mat.items():
            if "__" not in key:
                # print(f'{key}: {data_points[0]}')
                this_time_start = data_points[0][0]
                this_time_end = data_points[-1][0]
                if this_time_start < min_epoch_utc:
                    min_epoch_utc = this_time_start
                if this_time_end > max_epoch_utc:
                    max_epoch_utc = this_time_end

        duration_seconds = max_epoch_utc-min_epoch_utc

        # report start time
        local_dt = datetime.datetime.fromtimestamp(min_epoch_utc)
        date_time_string = local_dt.strftime("%I:%M:%S %p %Z on %m/%d/%Y ")
        duration_string = str(datetime.timedelta(seconds=duration_seconds))
        print(
            f'First datapoint was at: {date_time_string} (epoch: {min_epoch_utc})')
        print(f'Data duration (H:M:S): {duration_string}')

        # change start times
        for key, data_points in mat.items():
            if "__" not in key:
                for row in data_points:
                    row[0] = row[0]-min_epoch_utc

        print("Saving output .mat file...")
        input_file_name = os.path.basename(input_path)
        scipy.io.savemat(f'{output_path}\\{input_file_name}_seconds.mat', mat)
        print("Finished saving mat.")

        # CSV conversion
        print("Saving output .csv file...")
        log_data_seconds = convert_keys_to_relative_time(
            log_data, min_epoch_utc)
        interpolated_log_data_seconds = interpolate(
            log_data_seconds, timestep, duration_seconds, min_epoch_utc)
        save_dict_to_csv(interpolated_log_data_seconds,
                         f'{output_path}\\{input_file_name}_{timestep}ms_interp.csv')
        print("Finished saving csv.")
        # END CSV

        # Process succeeded
        return date_time_string

    except Exception as e:
        print("Error:", e)
        # Process failed
    return False


def browse_input_file():
    file_path = filedialog.askopenfilename(filetypes=[("BLF files", "*.blf")])
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)


def browse_output_folder():
    folder_path = filedialog.askdirectory(
        initialdir=get_default_download_path())
    if folder_path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, folder_path)


def process_files():
    # Reset success indicator
    message_label.config(text="Processing...", fg="black")
    root.update_idletasks()

    # Process data
    input_path = input_entry.get()
    output_path = output_entry.get()

    input_path = os.path.splitext(input_path)[0]
    timestamp = process_blf(input_path, output_path)

    # Set success indicator
    if timestamp is not False:
        message_label.config(
            text=f"Success. First timestamp: {timestamp}", fg="green")
        print("Completed with no errors.")
    else:
        message_label.config(text="Failure", fg="red")
        print("Failed, see error above.")


def get_default_download_path():
    # Get the path to the user's home directory
    home_dir = os.path.expanduser("~")
    # Append "Downloads" to the home directory path
    default_download_path = os.path.join(home_dir, "Downloads")
    return default_download_path


def resize_with_height(image_path, new_height):
    # Open the image
    img = Image.open(image_path)

    # Calculate the aspect ratio
    width_percent = new_height / float(img.size[1])
    new_width = int(float(img.size[0]) * width_percent)

    # Resize the image while maintaining the aspect ratio
    resized_img = img.resize((new_width, new_height))

    return resized_img


# Create the main window
root = tk.Tk()
root.title("BOLT BLF Processing Tool")

# Load logo image
logo_img = resize_with_height(f"{script_dir}\\bolt_logo.png", 100)
logo_img = ImageTk.PhotoImage(logo_img)

# Create logo label
logo_label = tk.Label(root, image=logo_img)
logo_label.grid(row=0, column=0, columnspan=3, padx=5, pady=5)

# Create input file selection
input_label = tk.Label(root, text="Input BLF File:")
input_label.grid(row=1, column=0, padx=5, pady=5)

input_entry = tk.Entry(root, width=50)
input_entry.grid(row=1, column=1, padx=5, pady=5)

input_button = tk.Button(root, text="Browse", command=browse_input_file)
input_button.grid(row=1, column=2, padx=5, pady=5)

# Create output folder selection
output_label = tk.Label(root, text="Output Folder:")
output_label.grid(row=2, column=0, padx=5, pady=5)

output_entry = tk.Entry(root, width=50)
output_entry.grid(row=2, column=1, padx=5, pady=5)

# Set default output path to Downloads
output_path = get_default_download_path()
# Insert default output path into the entry field
output_entry.insert(0, output_path)

output_button = tk.Button(root, text="Browse", command=browse_output_folder)
output_button.grid(row=2, column=2, padx=5, pady=5)

# Create process button
process_button = tk.Button(root, text="Process", command=process_files)
process_button.grid(row=3, column=1, padx=5, pady=10)

# Create message label
message_label = tk.Label(root, text="", fg="black")
message_label.grid(row=4, column=1, padx=5, pady=5)

# Run the Tkinter event loop
root.mainloop()
