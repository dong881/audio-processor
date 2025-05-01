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
        """處理行內格式如粗體、斜體、刪除線等"""
        if not text:
            return []
        
        # 初始化結果陣列
        result = []
        
        # 正則表達式模式，按優先順序排序
        patterns = [
            # 連結：[text](url)
            (r'\[([^\]]+)\]\(([^)]+)\)', lambda m: {
                "type": "text",
                "text": {
                    "content": m.group(1),
                    "link": {"url": m.group(2)}
                }
            }),
            # 代碼：`code`
            (r'`([^`]+)`', lambda m: {
                "type": "text",
                "text": {
                    "content": m.group(1)
                },
                "annotations": {
                    "code": True
                }
            }),
            # 粗體和斜體：***text*** or ___text___
            (r'(\*\*\*|___)(.*?)\1', lambda m: {
                "type": "text",
                "text": {
                    "content": m.group(2)
                },
                "annotations": {
                    "bold": True,
                    "italic": True
                }
            }),
            # 粗體：**text** or __text__
            (r'(\*\*|__)(.*?)\1', lambda m: {
                "type": "text",
                "text": {
                    "content": m.group(2)
                },
                "annotations": {
                    "bold": True
                }
            }),
            # 斜體：*text* or _text_
            (r'(\*|_)(.*?)\1', lambda m: {
                "type": "text",
                "text": {
                    "content": m.group(2)
                },
                "annotations": {
                    "italic": True
                }
            }),
            # 刪除線：~~text~~
            (r'~~(.*?)~~', lambda m: {
                "type": "text",
                "text": {
                    "content": m.group(1)
                },
                "annotations": {
                    "strikethrough": True
                }
            }),
        ]
        
        # 遍歷文本，查找和處理格式化內容
        remaining_text = text
        while remaining_text:
            # 尋找最先出現的格式化標記
            earliest_match = None
            earliest_pattern = None
            earliest_pos = float('inf')
            
            for pattern, formatter in patterns:
                match = re.search(pattern, remaining_text)
                if match and match.start() < earliest_pos:
                    earliest_pos = match.start()
                    earliest_match = match
                    earliest_pattern = formatter
            
            if earliest_match and earliest_pos < float('inf'):
                # 如果匹配前有普通文本，則先添加這段文本
                if earliest_pos > 0:
                    result.append({
                        "type": "text",
                        "text": {"content": remaining_text[:earliest_pos]}
                    })
                
                # 添加格式化的文本
                result.append(earliest_pattern(earliest_match))
                
                # 更新剩餘文本
                remaining_text = remaining_text[earliest_match.end():]
            else:
                # 沒有找到匹配，將剩餘文本作為普通文本添加
                if remaining_text:
                    result.append({
                        "type": "text",
                        "text": {"content": remaining_text}
                    })
                remaining_text = ""
        
        # 如果沒有任何格式化，則返回原始文本
        if not result and text:
            return [{"type": "text", "text": {"content": text}}]
            
        return result

    def split_transcript_into_blocks(self, transcript: str, max_length: int = 2000) -> List[Dict[str, Any]]:
        """將逐字稿分成適合 Notion API 的對話格式區塊"""
        blocks = []
        current_paragraph = ""
        
        lines = transcript.split("\n")
        for line in lines:
            # Check if the line appears to be a new speaker in a conversation
            speaker_match = re.match(r'^([A-Za-z0-9_\-]+):', line)
            
            # If we've hit max length or a new speaker, create a new block
            if (len(current_paragraph) + len(line) + 1 > max_length) or (speaker_match and current_paragraph):
                if current_paragraph:
                    # Format the current paragraph as a Notion paragraph block
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": self.process_inline_formatting(current_paragraph.strip())
                        }
                    })
                current_paragraph = line
            else:
                if current_paragraph:
                    current_paragraph += "\n" + line
                else:
                    current_paragraph = line
        
        # Don't forget the last paragraph
        if current_paragraph:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": self.process_inline_formatting(current_paragraph.strip())
                }
            })
        
        return blocks
        
    def create_notion_blocks(self, markdown_text: str, max_blocks_per_request: int = 90) -> List[List[Dict]]:
        """
        將Markdown文本轉換為Notion區塊並分批處理
        
        Args:
            markdown_text: Markdown格式的文本
            max_blocks_per_request: 每批次最大區塊數量 (Notion API限制為100)
            
        Returns:
            區塊分批列表，每批次不超過max_blocks_per_request
        """
        # 轉換為Notion API格式的區塊
        all_blocks = self.process_note_format_for_notion(markdown_text)
        
        # 如果區塊數量沒有超過限制，直接返回
        if len(all_blocks) <= max_blocks_per_request:
            return [all_blocks]
            
        # 分批處理區塊
        batches = []
        for i in range(0, len(all_blocks), max_blocks_per_request):
            batches.append(all_blocks[i:i + max_blocks_per_request])
            
        return batches
