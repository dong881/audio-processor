import re
from typing import List, Dict, Any


class NotionFormatter:
    def process_note_format_for_notion(self, text: str) -> list:
        """將Markdown文本處理成適合 Notion API 的格式"""
        blocks = []
        lines = text.split('\n')
        
        i = 0
        in_code_block = False
        code_block_content = ""
        code_language = ""
        in_quote = False
        quote_content = ""
        in_table = False
        table_rows = []
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳過空行，但保留在特殊區塊中的空行
            if not line:
                if in_code_block:
                    code_block_content += "\n"
                elif in_quote:
                    quote_content += "\n"
                i += 1
                continue
                
            # 處理代碼塊結束
            if in_code_block and line.startswith("```"):
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": code_block_content.strip()}}],
                        "language": code_language.lower() if code_language else "plain_text"
                    }
                })
                in_code_block = False
                code_block_content = ""
                code_language = ""
                i += 1
                continue
                
            # 收集代碼塊內容
            if in_code_block:
                code_block_content += line + "\n"
                i += 1
                continue
                
            # 處理代碼塊開始
            if line.startswith("```"):
                in_code_block = True
                if len(line) > 3:
                    code_language = line[3:].strip()
                i += 1
                continue
                
            # 處理表格結束（檢測到非表格行）
            if in_table and not line.startswith("|"):
                if table_rows:
                    # 創建表格區塊
                    table_block = {
                        "object": "block",
                        "type": "table",
                        "table": {
                            "table_width": len(table_rows[0]) if table_rows else 0,
                            "has_column_header": True,
                            "has_row_header": False,
                            "children": []
                        }
                    }
                    
                    # 添加表格行
                    for row_idx, row in enumerate(table_rows):
                        table_row = {
                            "object": "block",
                            "type": "table_row",
                            "table_row": {
                                "cells": []
                            }
                        }
                        
                        for cell in row:
                            table_row["table_row"]["cells"].append(
                                self.process_inline_formatting(cell.strip())
                            )
                            
                        table_block["table"]["children"].append(table_row)
                    
                    blocks.append(table_block)
                    
                in_table = False
                table_rows = []
                # 不增加 i，因為當前行需要用正常邏輯處理
            
            # 處理表格行
            elif in_table or line.startswith("|"):
                if not in_table:
                    in_table = True
                
                # 跳過分隔行（例如 |---|---|---| ）
                if not all(c == '-' or c == '|' or c == ' ' or c == ':' for c in line):
                    cells = line.split('|')
                    # 去掉首尾空元素（如果有）
                    if cells and not cells[0].strip():
                        cells.pop(0)
                    if cells and not cells[-1].strip():
                        cells.pop()
                        
                    table_rows.append(cells)
                i += 1
                continue
                
            # 處理引用結束（檢測到非引用行）
            if in_quote and not line.startswith('>'):
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": self.process_inline_formatting(quote_content.strip())
                    }
                })
                in_quote = False
                quote_content = ""
                # 不增加 i，因為當前行需要用正常邏輯處理
            
            # 處理引用行
            elif line.startswith('>'):
                if not in_quote:
                    in_quote = True
                    quote_content = ""
                    
                # 去除 > 符號並添加內容
                quote_content += line[1:].strip() + " "
                i += 1
                continue
                
            # 處理標題 (# 到 #####)
            if line.startswith('#'):
                # 計算 # 的數量
                heading_level = 0
                for char in line:
                    if char == '#':
                        heading_level += 1
                    else:
                        break
                        
                # Notion API 最高支持到 heading_3
                if heading_level > 3:
                    heading_level = 3
                    
                heading_text = line[heading_level:].strip()
                # 應用行內格式化處理
                rich_text_content = self.process_inline_formatting(heading_text)
                
                blocks.append({
                    "object": "block",
                    "type": f"heading_{heading_level}",
                    f"heading_{heading_level}": {
                        "rich_text": rich_text_content
                    }
                })
                
            # 處理待辦事項 ([ ] 或 [x])
            elif line.startswith('[ ]') or line.startswith('[x]') or line.startswith('[X]'):
                checked = line.startswith('[x]') or line.startswith('[X]')
                content = line[3:].strip()
                # 應用行內格式化處理
                rich_text_content = self.process_inline_formatting(content)
                
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": rich_text_content,
                        "checked": checked
                    }
                })
            
            # 處理編號列表 (1. 2. 等)
            elif re.match(r'^\d+\.\s', line):
                content = re.sub(r'^\d+\.\s', '', line).strip()
                # 應用行內格式化處理
                rich_text_content = self.process_inline_formatting(content)
                
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": rich_text_content
                    }
                })
            
            # 處理項目符號列表 (- * +)
            elif line.startswith('-') or line.startswith('*') or line.startswith('+'):
                content = line[1:].strip()
                # 應用行內格式化處理 - 修復此處不支援格式化的問題
                rich_text_content = self.process_inline_formatting(content)
                
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text_content
                    }
                })
                
            # 處理水平線
            elif line == '---' or line == '***' or line == '___':
                blocks.append({
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                })
                
            # 普通段落
            else:
                # 處理粗體、斜體等格式
                rich_text_content = self.process_inline_formatting(line)
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": rich_text_content
                    }
                })
                
            i += 1
            
        # 處理未關閉的區塊
        if in_code_block and code_block_content:
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": code_block_content.strip()}}],
                    "language": code_language.lower() if code_language else "plain_text"
                }
            })
            
        if in_quote and quote_content:
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": self.process_inline_formatting(quote_content.strip())
                }
            })
            
        if in_table and table_rows:
            # 創建表格區塊
            table_block = {
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": len(table_rows[0]) if table_rows else 0,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": []
                }
            }
            
            # 添加表格行
            for row_idx, row in enumerate(table_rows):
                table_row = {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": []
                    }
                }
                
                for cell in row:
                    table_row["table_row"]["cells"].append(
                        self.process_inline_formatting(cell.strip())
                    )
                    
                table_block["table"]["children"].append(table_row)
            
            blocks.append(table_block)
                
        return blocks

    def process_inline_formatting(self, text: str) -> list:
        """處理行內格式化（粗體、斜體、代碼等）"""
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        # 處理行內代碼（使用反引號 `code`）
        pattern_inline_code = r'`([^`]+)`'
        
        # 處理粗體（使用雙星號 **bold**）
        pattern_bold = r'\*\*(.*?)\*\*'
        
        # 處理斜體（使用單星號 *italic*）
        pattern_italic = r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)'
        
        # 處理刪除線（使用雙波浪線 ~~strikethrough~~）
        pattern_strikethrough = r'~~(.*?)~~'
        
        # 處理連結（使用 [text](url) 格式）
        pattern_link = r'\[(.*?)\]\((.*?)\)'
        
        # 儲存所有的格式化區段
        segments = []
        
        # 目前處理到的位置
        current_pos = 0
        
        # 請求粗體、斜體、刪除線和代碼的所有匹配
        all_matches = []
        
        # 收集所有格式匹配
        for pattern, format_type in [
            (pattern_inline_code, "code"),
            (pattern_bold, "bold"),
            (pattern_italic, "italic"),
            (pattern_strikethrough, "strikethrough"),
            (pattern_link, "link")
        ]:
            for match in re.finditer(pattern, text):
                # 存儲匹配的開始位置、結束位置和標籤類型
                if format_type == "link":
                    link_text = match.group(1)
                    link_url = match.group(2)
                    all_matches.append((match.start(), match.end(), format_type, link_text, link_url))
                else:
                    all_matches.append((match.start(), match.end(), format_type, match.group(1)))
        
        # 按開始位置排序匹配項
        all_matches.sort(key=lambda x: x[0])
        
        # 檢查匹配項是否有交疊
        valid_matches = []
        for i, match in enumerate(all_matches):
            start, end = match[0], match[1]
            # 檢查此匹配是否與之前的有效匹配交疊
            is_valid = True
            for valid_start, valid_end, _, *_ in valid_matches:
                # 如果此匹配與之前的有效匹配交疊，標記為無效
                if (start < valid_end and end > valid_start):
                    is_valid = False
                    break
            if is_valid:
                valid_matches.append(match)
        
        # 依次處理每個有效匹配，並將普通文本作為純文本段添加
        for match in valid_matches:
            start, end, format_type, *format_args = match
            
            # 添加當前位置到匹配開始之間的純文本
            if start > current_pos:
                segments.append({
                    "type": "text",
                    "text": {"content": text[current_pos:start]}
                })
            
            # 根據格式類型添加格式化的文本
            if format_type == "link":
                link_text, link_url = format_args
                segments.append({
                    "type": "text",
                    "text": {
                        "content": link_text,
                        "link": {"url": link_url}
                    }
                })
            else:
                # 創建帶有匹配格式的文本
                formatted_text = {
                    "type": "text",
                    "text": {"content": format_args[0]}
                }
                
                # 添加相應的格式標記
                if format_type == "bold":
                    formatted_text["annotations"] = {"bold": True}
                elif format_type == "italic":
                    formatted_text["annotations"] = {"italic": True}
                elif format_type == "strikethrough":
                    formatted_text["annotations"] = {"strikethrough": True}
                elif format_type == "code":
                    formatted_text["annotations"] = {"code": True}
                
                segments.append(formatted_text)
            
            # 更新當前位置
            current_pos = end
        
        # 添加最後一部分純文本（如果有）
        if current_pos < len(text):
            segments.append({
                "type": "text",
                "text": {"content": text[current_pos:]}
            })
                
        # 如果沒有任何格式化匹配，返回整個文本作為純文本
        if not segments:
            return [{"type": "text", "text": {"content": text}}]
            
        return segments

    def split_transcript_into_blocks(self, transcript: str, max_length: int = 2000) -> List[Dict[str, Any]]:
        """將逐字稿拆分成多個區塊，每個區塊不超過指定長度"""
        blocks = []
        lines = transcript.strip().split('\n')
        
        current_block_lines = []
        current_length = 0
        
        for line in lines:
            # 檢查當前行加上當前區塊是否會超過最大長度
            if current_length + len(line) + 1 > max_length and current_block_lines:  # +1 是為了換行符
                # 當前區塊已滿，創建一個新區塊
                block_text = '\n'.join(current_block_lines)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": block_text}}]
                    }
                })
                # 重置當前區塊
                current_block_lines = [line]
                current_length = len(line)
            else:
                # 當前行可以添加到當前區塊
                current_block_lines.append(line)
                current_length += len(line) + 1  # +1 是為了換行符
        
        # 處理最後一個區塊
        if current_block_lines:
            block_text = '\n'.join(current_block_lines)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": block_text}}]
                }
            })
        
        return blocks

    def create_notion_blocks(self, markdown_text: str, max_blocks_per_request: int = 90) -> List[List[Dict]]:
        """將 Markdown 文本處理成多批 Notion 區塊"""
        all_blocks = self.process_note_format_for_notion(markdown_text)
        
        # 將區塊分批，每批不超過指定的最大區塊數
        batches = []
        for i in range(0, len(all_blocks), max_blocks_per_request):
            batch = all_blocks[i:i + max_blocks_per_request]
            batches.append(batch)
            
        return batches 