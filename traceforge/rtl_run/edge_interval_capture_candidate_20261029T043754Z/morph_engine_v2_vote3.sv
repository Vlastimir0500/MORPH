module morph_engine_v2 (
    input logic clk,
    input logic rst_n,
    input logic program_mode,
    input logic program_high_byte,
    input logic [5:0] program_addr,
    input logic [7:0] program_byte,
    input logic [7:0] pin_in,
    output logic [7:0] pin_out,
    output logic [7:0] pin_oe,
    output logic sample_reg,
    output logic [7:0] shift_reg,
    output logic timed_out,
    output logic fault
);

    logic [15:0] prog_mem [0:63];
    logic [2:0] sample_history;
    logic [5:0] pc;
    logic [15:0] ir;
    logic [7:0] wait_count;
    logic [5:0] loop_remaining;
    logic [5:0] loop_pc;
    logic [5:0] loop_target;
    logic loop_active;
    logic [7:0] pin_prev;
    logic [15:0] cycle_counter;
    logic [15:0] edge_last_cycle;
    logic [15:0] edge_interval;
    logic edge_seen;
    logic edge_capture_valid;
    logic [2:0] state;

    localparam FETCH = 3'd0;
    localparam EXEC = 3'd1;
    localparam WAIT_STATE = 3'd2;
    localparam EDGE_WAIT = 3'd3;
    localparam HALT = 3'd4;

    always_ff @(posedge clk) begin
        if (rst_n && program_mode) begin
            if (program_high_byte)
                prog_mem[program_addr][15:8] <= program_byte;
            else
                prog_mem[program_addr][7:0] <= program_byte;
        end

        if (!rst_n || program_mode) begin
            pc <= 6'd0;
            ir <= 16'd0;
            wait_count <= 8'd0;
            loop_remaining <= 6'd0;
            loop_pc <= 6'd0;
            loop_target <= 6'd0;
            loop_active <= 1'b0;
            pin_prev <= pin_in;
            cycle_counter <= 16'd0;
            edge_last_cycle <= 16'd0;
            edge_interval <= 16'd0;
            edge_seen <= 1'b0;
            edge_capture_valid <= 1'b0;
            sample_reg <= 1'b0;
            sample_history <= 3'b000;
            shift_reg <= 8'd0;
            pin_out <= 8'd0;
            pin_oe <= 8'd0;
            timed_out <= 1'b0;
            fault <= 1'b0;
            state <= FETCH;
        end else begin
            pin_prev <= pin_in;
            cycle_counter <= cycle_counter + 1'b1;

            case (state)
                FETCH: begin
                    ir <= prog_mem[pc];
                    state <= EXEC;
                end

                EXEC: begin
                    case (ir[15:12])
                        4'h0: begin
                            state <= HALT;
                        end

                        4'h1: begin
                            if (ir[11:8] <= 4'd7) begin
                                pin_out[ir[10:8]] <= ir[0];
                                pin_oe[ir[10:8]] <= 1'b1;
                                pc <= pc + 1'b1;
                                state <= FETCH;
                            end else begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                state <= HALT;
                            end
                        end

                        4'h2: begin
                            if (ir[11:8] <= 4'd7) begin
                                sample_reg <= pin_in[ir[10:8]];
                                sample_history <= {sample_history[1:0], pin_in[ir[10:8]]};
                                pc <= pc + 1'b1;
                                state <= FETCH;
                            end else begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                state <= HALT;
                            end
                        end

                        4'h3: begin
                            if (ir[7:0] == 0) begin
                                pc <= pc + 1'b1;
                                state <= FETCH;
                            end else begin
                                wait_count <= ir[7:0];
                                state <= WAIT_STATE;
                            end
                        end

                        4'h4: begin
                            if (ir[11:8] <= 4'd7) begin
                                wait_count <= {1'b0, ir[7:1]};
                                state <= EDGE_WAIT;
                            end else begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                state <= HALT;
                            end
                        end

                        4'h5: begin
                            shift_reg <= {shift_reg[6:0], sample_reg};
                            pc <= pc + 1'b1;
                            state <= FETCH;
                        end

                        4'h6: begin
                            if (loop_active && ((ir[5:0] < loop_target) || (ir[5:0] > loop_pc))) begin
                                loop_active <= 1'b0;
                                loop_remaining <= 6'd0;
                            end
                            pc <= ir[5:0];
                            state <= FETCH;
                        end

                        4'h7: begin
                            if (ir[11:8] <= 4'd7) begin
                                pin_out[ir[10:8]] <= 1'b0;
                                pin_oe[ir[10:8]] <= 1'b0;
                                pc <= pc + 1'b1;
                                state <= FETCH;
                            end else begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                state <= HALT;
                            end
                        end

                        4'h8: begin
                            if (sample_reg == ir[7]) begin
                                if (loop_active && ((ir[5:0] < loop_target) || (ir[5:0] > loop_pc))) begin
                                    loop_active <= 1'b0;
                                    loop_remaining <= 6'd0;
                                end
                                pc <= ir[5:0];
                            end else begin
                                pc <= pc + 1'b1;
                            end
                            state <= FETCH;
                        end

                        4'h9: begin
                            if ((ir[11:6] == 6'd0) || (ir[5:0] >= pc)) begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                loop_active <= 1'b0;
                                loop_remaining <= 6'd0;
                                state <= HALT;
                            end else if (!loop_active) begin
                                if (ir[11:6] == 6'd1) begin
                                    loop_remaining <= 6'd0;
                                    pc <= pc + 1'b1;
                                    state <= FETCH;
                                end else begin
                                    loop_active <= 1'b1;
                                    loop_pc <= pc;
                                    loop_target <= ir[5:0];
                                    loop_remaining <= ir[11:6] - 1'b1;
                                    pc <= ir[5:0];
                                    state <= FETCH;
                                end
                            end else if (loop_pc == pc) begin
                                if (loop_remaining > 6'd1) begin
                                    loop_remaining <= loop_remaining - 1'b1;
                                    pc <= loop_target;
                                    state <= FETCH;
                                end else begin
                                    loop_active <= 1'b0;
                                    loop_remaining <= 6'd0;
                                    pc <= pc + 1'b1;
                                    state <= FETCH;
                                end
                            end else begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                loop_active <= 1'b0;
                                loop_remaining <= 6'd0;
                                state <= HALT;
                            end
                        end

                        4'hA: begin
                            sample_reg <=
                                (sample_history[2] & sample_history[1]) |
                                (sample_history[2] & sample_history[0]) |
                                (sample_history[1] & sample_history[0]);
                            pc <= pc + 1'b1;
                            state <= FETCH;
                        end

                                                4'hB: begin
                            if (ir[11:8] <= 4'd7) begin
                                wait_count <= 8'd0;
                                state <= EDGE_WAIT;
                            end else begin
                                fault <= 1'b1;
                                pin_oe <= 8'd0;
                                state <= HALT;
                            end
                        end

default: begin
                            fault <= 1'b1;
                            pin_oe <= 8'd0;
                            state <= HALT;
                        end
                    endcase
                end

                WAIT_STATE: begin
                    if (wait_count <= 1) begin
                        wait_count <= 8'd0;
                        pc <= pc + 1'b1;
                        state <= FETCH;
                    end else begin
                        wait_count <= wait_count - 1'b1;
                    end
                end

                EDGE_WAIT: begin
                    if ((ir[0] && pin_in[ir[10:8]] && !pin_prev[ir[10:8]]) ||
                        (!ir[0] && !pin_in[ir[10:8]] && pin_prev[ir[10:8]])) begin
                        if (ir[15:12] == 4'hB) begin
                            if (edge_seen) begin
                                edge_interval <= cycle_counter - edge_last_cycle;
                                edge_capture_valid <= 1'b1;
                            end
                            edge_last_cycle <= cycle_counter;
                            edge_seen <= 1'b1;
                        end
                        wait_count <= 8'd0;
                        pc <= pc + 1'b1;
                        state <= FETCH;
                    end else if (wait_count != 0) begin
                        if (wait_count <= 1) begin
                            wait_count <= 8'd0;
                            timed_out <= 1'b1;
                            fault <= 1'b1;
                            pin_oe <= 8'd0;
                            state <= HALT;
                        end else begin
                            wait_count <= wait_count - 1'b1;
                        end
                    end
                end

                HALT: begin
                    state <= HALT;
                end

                default: begin
                    fault <= 1'b1;
                    pin_oe <= 8'd0;
                    state <= HALT;
                end
            endcase
        end
    end

endmodule
