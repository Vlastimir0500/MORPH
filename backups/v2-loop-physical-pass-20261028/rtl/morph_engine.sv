module morph_engine (
    input  logic clk,
    input  logic rst_n,
    input  logic prog_we,
    input  logic [3:0] prog_addr,
    input  logic [15:0] prog_data,
    input  logic pin_in,
    output logic pin_out,
    output logic sample_reg,
    output logic [7:0] shift_reg
);

logic [15:0] prog_mem [0:15];
logic [3:0] pc;
logic [15:0] ir;
logic [7:0] wait_count;
logic pin_prev;
logic [1:0] state;

localparam FETCH = 2'd0;
localparam EXEC = 2'd1;
localparam WAIT_STATE = 2'd2;
localparam EDGE_WAIT = 2'd3;

always_ff @(posedge clk) begin
    if (prog_we)
        prog_mem[prog_addr] <= prog_data;

    if (!rst_n) begin
        pc <= 4'd0;
        ir <= 16'd0;
        wait_count <= 8'd0;
        pin_prev <= 1'b0;
        sample_reg <= 1'b0;
        shift_reg <= 8'd0;
        pin_out <= 1'b0;
        state <= FETCH;
    end else begin
        pin_prev <= pin_in;

        case (state)

            FETCH: begin
                ir <= prog_mem[pc];
                state <= EXEC;
            end

            EXEC: begin
                case (ir[15:12])

                    4'h1: begin
                        pin_out <= ir[0];
                        pc <= pc + 1'b1;
                        state <= FETCH;
                    end

                    4'h2: begin
                        sample_reg <= pin_in;
                        pc <= pc + 1'b1;
                        state <= FETCH;
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
                        state <= EDGE_WAIT;
                    end

                    4'h5: begin
                        shift_reg <= {shift_reg[6:0], sample_reg};
                        pc <= pc + 1'b1;
                        state <= FETCH;
                    end

                    4'h6: begin
                        pc <= ir[3:0];
                        state <= FETCH;
                    end

                    default: begin
                        pc <= pc + 1'b1;
                        state <= FETCH;
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
                if (ir[0]) begin
                    if (pin_in && !pin_prev) begin
                        pc <= pc + 1'b1;
                        state <= FETCH;
                    end
                end else begin
                    if (!pin_in && pin_prev) begin
                        pc <= pc + 1'b1;
                        state <= FETCH;
                    end
                end
            end

        endcase
    end
end

endmodule
