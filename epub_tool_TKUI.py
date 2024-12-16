import tkinter as tk
from tkinter.filedialog import askopenfiles
from tkinter import filedialog, ttk, NSEW, BOTH, messagebox
import os

root = tk.Tk()
root.title("Epub Tool")
root.minsize(600, 600)
root.resizable(True, True)
tmp_files_dic = {}


def store_file(files):
    for file in files:
        if file not in tmp_files_dic:
            tmp_files_dic[file] = 1


def select_dir():
    dir = filedialog.askdirectory(title="选择文件夹")
    # 遍历文件夹所有文件
    tmp_files = []
    for root, dirs, files in os.walk(dir):
        for file in files:
            if file.endswith(".epub"):
                tmp_files.append(os.path.normpath(os.path.join(root, file)))
    store_file(tmp_files)
    display_added_file(tmp_files_dic.keys())


def add_file():
    files = filedialog.askopenfilenames(title="选择文件")
    tmp_files = []
    for file in files:
        if file.endswith(".epub"):
            tmp_files.append(os.path.normpath(file))
    store_file(files)
    display_added_file(tmp_files_dic.keys())


def delete_selected():
    # 获取所有选中的项（返回的是一个元组）
    selected_indices = file_list.curselection()

    if not selected_indices:
        messagebox.showwarning("Warning", "未选中任何文件")
        return
    print(selected_indices)
    # 由于删除操作会改变列表框中的索引，所以需要从后往前删除
    for index in reversed(selected_indices):
        del tmp_files_dic[file_list.get(index)]  # 删除元素
        file_list.delete(index)


def delete_all():
    file_list.delete(0, tk.END)
    tmp_files_dic.clear()


def display_added_file(files):
    file_list.delete(0, tk.END)
    for file in files:
        file_list.insert(tk.END, file)


frame1 = tk.Frame(root)
frame1.pack(pady=5)
add_files_btn = tk.Button(frame1, text="添加文件", command=add_file)
add_files_btn.pack(side=tk.LEFT, padx=5)
select_dir_btn = tk.Button(frame1, text="添加文件夹", command=select_dir)
select_dir_btn.pack(side=tk.LEFT, padx=5)
delete_button = tk.Button(frame1, text="删除所选", command=delete_selected)
delete_button.pack(side=tk.LEFT, padx=5)
delete_all_button = tk.Button(
    frame1, text="删除全部", command=lambda: file_list.delete(0, tk.END)
)
delete_all_button.pack(side=tk.LEFT, padx=5)


def start_progress():
    file_count = len(file_list.get(0, tk.END))
    if file_count == 0:
        messagebox.showwarning("Warning", "未添加任何文件")
        return
    progress["value"] = 0
    progress["maximum"] = file_count
    root.update_idletasks()
    for i in range(file_count):
        progress["value"] += 1
        root.update_idletasks()
        root.after(50)  # 模拟任务的延迟
        file_path = file_list.get(0)
        file_list.delete(0)
        tmp_files_dic.pop(file_path)
        result_list.insert(tk.END, f"处理完成...文件: {file_path}")


frame2 = tk.Frame(root)
frame2.pack(pady=5)
reformat_btn = tk.Button(frame2, text="格式化", command=start_progress)
reformat_btn.pack(side=tk.LEFT, padx=5)
encrypt_btn = tk.Button(frame2, text="加密", command=start_progress)
encrypt_btn.pack(side=tk.LEFT, padx=5)
decrypt_btn = tk.Button(frame2, text="解密", command=start_progress)
decrypt_btn.pack(side=tk.LEFT, padx=5)


def show_output_dir():
    output_dir = filedialog.askdirectory(title="选择输出文件夹")
    if output_dir:
        output_dir_label.config(text=f"输出路径: {output_dir}")
    print(output_dir)


frame3 = tk.Frame(root)
frame3.pack(pady=5)
frame3.pack(pady=5)
# 创建一个标签用于显示输出路径
output_dir_label = tk.Label(frame3, text="默认输出路径: 默认文件所在路径")
output_dir_label.pack(side=tk.LEFT, padx=5)
show_btn = tk.Button(frame3, text="选择输出路径", command=show_output_dir)
show_btn.pack(side=tk.LEFT, padx=5)

# 创建一个 Frame 用于放置进度条
progress_frame = tk.Frame(root)
progress_frame.pack(fill=tk.X, padx=10, pady=5)

# 创建进度条
progress = ttk.Progressbar(
    progress_frame, orient=tk.HORIZONTAL, length=400, mode="determinate"
)
progress.pack(fill=tk.X, padx=5, pady=5)


# 创建一个 Frame 用于放置 Listbox 和 Scrollbar
listbox_frame = tk.Frame(root)
listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
listbox_label = tk.Label(listbox_frame, text="输入文件列表")
listbox_label.grid(row=0, column=0, sticky=tk.W, padx=5)
# 创建 Listbox
file_list = tk.Listbox(listbox_frame, selectmode=tk.EXTENDED)
file_list.grid(row=1, column=0, sticky=tk.NSEW)

# 创建垂直 Scrollbar
v_scrollbar = tk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=file_list.yview)
v_scrollbar.grid(row=1, column=1, sticky=tk.NS)

# 创建水平 Scrollbar
h_scrollbar = tk.Scrollbar(listbox_frame, orient=tk.HORIZONTAL, command=file_list.xview)
h_scrollbar.grid(row=2, column=0, sticky=tk.EW)

# 将 Scrollbar 绑定到 Listbox
file_list.config(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

# 配置 grid 行列权重
listbox_frame.grid_rowconfigure(0, weight=1)
listbox_frame.grid_columnconfigure(0, weight=1)


"""

"""

# 创建一个 Frame 用于放置 Listbox 和 Scrollbar
result_box_frame = tk.Frame(root)
result_box_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
result_box_lable = tk.Label(result_box_frame, text="执行结果")
result_box_lable.grid(row=0, column=0, sticky=tk.W, padx=5)
# 创建 Listbox
result_list = tk.Listbox(result_box_frame, selectmode=tk.EXTENDED)
result_list.grid(row=1, column=0, sticky=tk.NSEW)

# 创建垂直 Scrollbar
v_scrollbar = tk.Scrollbar(
    result_box_frame, orient=tk.VERTICAL, command=file_list.yview
)
v_scrollbar.grid(row=1, column=1, sticky=tk.NS)

# 创建水平 Scrollbar
h_scrollbar = tk.Scrollbar(
    result_box_frame, orient=tk.HORIZONTAL, command=file_list.xview
)
h_scrollbar.grid(row=2, column=0, sticky=tk.EW)

# 将 Scrollbar 绑定到 Listbox
result_list.config(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

# 配置 grid 行列权重
result_box_frame.grid_rowconfigure(0, weight=1)
result_box_frame.grid_columnconfigure(0, weight=1)

root.mainloop()
